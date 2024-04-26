#! /usr/bin/env python3.8

import ansible_runner
import ansiconv
import argparse
import glob
import inspect
import libvirt
import logging
import os
import os
import pwd
import re
import socket
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import yaml

from textwrap import dedent
from uuid import uuid4

# create a content manager to wrap the libvirt connection so we can periodically restart it cleanly
class LibvirtConnection:
    def __init__(self, uri='qemu:///system'):
        self.conn = None
        self.uri = uri

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn is not None:
            self.conn.close()

    def restart(self):
        if self.conn is not None:
            logger = logging.getLogger(__name__)
            self.conn.close()
            time.sleep(5)
            logger.info("Restarting libvirt network")
            run_command(["systemctl", "restart", "virtlogd.socket"])
            run_command(["systemctl", "restart", "libvirtd"])
            time.sleep(5)
            self._connect()

    def _connect(self):
        self.conn = libvirt.open(self.uri)
        if self.conn is None:
            logger = logging.getLogger(__name__)
            logger.info(f"Failed to open connection to {self.uri}")
            sys.exit(1)

    def __getattr__(self, name):
        # Forward attribute accesses to the underlying conn object
        return getattr(self.conn, name)

def run_command(command):
    logger = logging.getLogger(__name__)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()
    if stdout:
        logger.info(stdout.strip())
    if stderr:
        logger.error(stderr.strip())
    return process.returncode

def setup_logging(verbose_log,concise_log):
    filemode='w' # TODO: make this the same across the program
    # Configure the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # Root logger captures all levels

    # Handler for verbose log file (captures everything)
    verbose_file_handler = logging.FileHandler(verbose_log, mode=filemode)
    verbose_file_handler.setLevel(logging.DEBUG)
    verbose_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    verbose_file_handler.setFormatter(verbose_format)

    # Handler for concise log file (captures warnings and errors only)
    concise_file_handler = logging.FileHandler(concise_log, mode=filemode)
    concise_file_handler.setLevel(logging.WARNING)
    concise_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    concise_file_handler.setFormatter(concise_format)

    # Console handler that replicates the verbose file handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)

    # Add handlers to the logger
    logger.addHandler(verbose_file_handler)
    logger.addHandler(concise_file_handler)
    logger.addHandler(console_handler)

def wait_for_ssh_with_ansible(host, ansible_verbosity, timeout=300): 
    playbook_content = dedent(f"""
    ---
    - name: Wait for SSH to become available
      hosts: localhost 
      tasks:
        - name: Wait for SSH to be available on host {host}
          wait_for:
            host: "{host}"
            port: 22
            state: started
            timeout: {timeout}
    """)

    # Create a temporary playbook file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yml') as temp_playbook:
        temp_playbook.write(playbook_content)
        temp_playbook_path = temp_playbook.name

    try:
        logger = logging.getLogger(__name__)
        logger.debug(f"Using ansible playbook {temp_playbook_path} to wait up to {timeout} seconds for {host} to boot.")
        # Run the playbook
        r = ansible_runner.run(
            playbook=temp_playbook_path,
            inventory=f'{host},',  # Comma is needed for a single host
        )
        if r.status == 'successful':
            logger.debug(f"SSH is available on {host}.")
            return True
        else:
            logger.debug(f"Failed to connect to {host} via SSH.")
            return False
    finally:
        # Clean up the temporary playbook file
        os.remove(temp_playbook_path)
        pass

def create_kickstart_file(hostname, ks_dir, ks_file, baseos_location, root_password, ssh_pub):
    logger = logging.getLogger(__name__)
    os.makedirs(ks_dir, exist_ok=True)
    logger.debug(f"Creating kickstart file {ks_dir}/{ks_file}")
    #repo --name="AppStream" --baseurl={appstream_location}
    with open(f"{ks_dir}/{ks_file}", "w") as ks:
        ks_contents = dedent(f"""\
            #version=RHEL8
            text
            repo --name="AppStream" --baseurl=
            %packages
            @^minimal-environment
            kexec-tools
            %end
            lang en_US.UTF-8
            network  --hostname={hostname}
            url --url="{baseos_location}"
            firstboot --enable
            skipx
            ignoredisk --only-use=vda
            bootloader --append="crashkernel=auto" --location=mbr --boot-drive=vda
            autopart
            clearpart --all --initlabel --drives=vda
            timezone US/Mountain --isUtc --ntpservers=0.pool.ntp.org,1.pool.ntp.org,2.pool.ntp.org,3.pool.ntp.org
            {"rootpw --plaintext " + root_password if root_password else ""}
            %addon com_redhat_kdump --enable --reserve-mb='auto'
            %end
            %anaconda
            pwpolicy root --minlen=6 --minquality=1 --notstrict --nochanges --notempty
            pwpolicy user --minlen=6 --minquality=1 --notstrict --nochanges --emptyok
            pwpolicy luks --minlen=6 --minquality=1 --notstrict --nochanges --notempty
            %end
            %post
            mkdir -p /root/.ssh
            chmod 700 /root/.ssh
            echo "{ssh_pub}" >> /root/.ssh/authorized_keys
            chmod 600 /root/.ssh/authorized_keys
            reboot 
            %end
        """).strip().splitlines()
            #shutdown -P now # don't do the shutdown in the kickstart, then we can use ssh to poll and know when install is done
        # remove leading whitespace and empty lines
        ks_contents = os.linesep.join([line.lstrip() for line in ks_contents if line.strip()])
        ks.write(ks_contents)

def install_initial_vm(conn, hostname, inventory, ansible_verbosity): 
    logger = logging.getLogger(__name__)
    # Prepare kickstart file
    ks_dir = "/tmp/kickstart_files"
    ks_file = f"{hostname}.kickstart"
    baseos_location = get_inventory_value(inventory, 'all.vars.bootstrap_vm.location')
    root_password   = get_inventory_value(inventory, 'all.vars.bootstrap_vm.root_pwd')
    auth_keys       = get_inventory_value(inventory, 'all.vars.bootstrap_vm.auth_keys')
    cpus            = get_inventory_value(inventory, 'all.vars.bootstrap_vm.cpus')
    memory          = get_inventory_value(inventory, 'all.vars.bootstrap_vm.memory_mbs')
    disk_size       = get_inventory_value(inventory, 'all.vars.bootstrap_vm.boot_hdd_gbs')
    ssh_pub         = open(auth_keys).read().strip()
    create_kickstart_file(hostname, ks_dir, ks_file, baseos_location, root_password, ssh_pub)

    wait_minutes = 20
    command = f"""
    virt-install \
    --name "{hostname}" \
    --ram "{memory}" \
    --vcpus "{cpus}" \
    --disk path=/var/lib/libvirt/images/"{hostname}".img,size="{disk_size}" \
    --os-type linux \
    --os-variant centos8 \
    --network network=default \
    --graphics none \
    --initrd-inject "{ks_dir}/{ks_file}" \
    --location "{baseos_location}" \
    --noautoconsole \
    --wait {wait_minutes} \
    --extra-args 'inst.ks=file:/{ks_file} console=tty0 console=ttyS0,115200n8'
    """
    #--noreboot \ # try without the noreboot and see if that helps
    logger.debug(f"Creating VM {hostname} from {baseos_location}")
    logger.debug(f"{command}")
    start_time = time.time()
    result = subprocess.run(command, shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        error_message = f"Warning message: Potential failure to create VM {hostname}:\n" \
                        f"Return code: {result.returncode}\n" \
                        f"Standard Output: {result.stdout.strip()}\n" \
                        f"Standard Error: {result.stderr.strip()}"
        logger.error(error_message)
        if 'Installation has exceeded specified time limit. Exiting application.' in result.stdout:
            logger.debug("Ignoring timeout error from virt-install.")
        else:
            Fatal(error_message)
    if result.stdout:
        logger.debug(result.stdout.strip())
    if result.stderr:
        logger.error(result.stderr.strip())
    elapsed = time.time() - start_time

    # Restart the VM and wait for it
    logger.debug(f"Created VM {hostname} in {elapsed} seconds. Will now restart it.")
    restart_domain(conn, hostname)
    wait_for_ssh_with_ansible(hostname, ansible_verbosity)

    # Clear out any old hostnames
    logger.debug(f"Removing any old ssh hostname entries for {hostname}")
    # TODO: create a helper function for remove old host keys
    run_command(["ssh-keygen", "-R", hostname])

# TODO: This function takes a long time to run.
# might be good to add more debugging info to see which steps take so long
def restore_vm_from_stash(conn, src_path, xml_file_path, pool_name, vmname):
    """
    Restore a VM from a stashed image and XML configuration.

    Args:
        conn (libvirt.virConnect): The libvirt connection object.
        src_path (str): The path to the stashed image.
        xml_file_path (str): The path to the stashed XML configuration file.
        pool_name (str): The name of the libvirt storage pool to use.
        vmname (str): The name of the VM to be restored.
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Restoring VM {vmname} from stashed configuration {src_path}")

    # Read the XML configuration from the stashed file
    with open(xml_file_path, 'r') as xml_file:
        xml_desc = xml_file.read()

    # Get the storage pool
    pool = conn.storagePoolLookupByName(pool_name)
    if pool is None:
        raise Exception(f"Storage pool {pool_name} not found")

    # Refresh the pool to ensure it's up-to-date
    pool.refresh(0)

    # Copy the stashed disk image to a temporary location
    tmp_path = f"/tmp/{vmname}.img"
    shutil.copy2(src_path, tmp_path)

    # Create a new storage volume for the restored image in the pool
    vol_xml = f"""
    <volume>
        <name>{vmname}.img</name>
        <capacity unit="bytes">{os.path.getsize(tmp_path)}</capacity>
        <allocation unit="bytes">{os.path.getsize(tmp_path)}</allocation>
        <target>
            <format type="qcow2"/>
            <permissions>
                <mode>0644</mode>
            </permissions>
        </target>
    </volume>
    """
    vol = pool.createXML(vol_xml, 0)
    if vol is None:
        raise Exception("Failed to create storage volume")

    # Upload the image data to the new volume
    stream = conn.newStream(0)
    vol.upload(stream, 0, os.path.getsize(tmp_path), flags=0)
    with open(tmp_path, "rb") as file:
        stream.sendAll(lambda stream, buf, opaque: file.read(buf), None)
    stream.finish()
    os.remove(tmp_path)

    # Get the path of the new volume
    dst_path = vol.path()

    # Update the XML configuration to use the new storage volume
    xml_root = ET.fromstring(xml_desc)
    disk_elements = xml_root.findall(".//disk/source[@file]")
    if disk_elements:
        disk_elements[0].set('file', dst_path)
        updated_xml = ET.tostring(xml_root, encoding='unicode')
    else:
        raise Exception("No disk element found in XML")

    # Define the VM from the updated XML configuration
    dom = conn.defineXML(updated_xml)
    if dom is None:
        raise Exception(f"Failed to define the domain {vmname} from updated XML")

    logger.debug(f"Restored VM {vmname} from stashed configuration")

def setup_ssh_key_and_copy_to_guest(guest_mount_path, key_name="id_rsa"):
    """
    Checks for an SSH key pair in $HOME/.ssh, creates one if it doesn't exist,
    and then copies the public key into the specified guest mount directory.

    Args:
        guest_mount_path (str): The path to the guest mount directory.
        key_name (str): The name of the SSH key pair (default: "id_rsa").
    """
    logger = logging.getLogger(__name__)
    ssh_dir = os.path.join(os.environ['HOME'], '.ssh')
    private_key_path = os.path.join(ssh_dir, key_name)
    public_key_path = private_key_path + '.pub'

    # Check if the SSH key pair exists, create if it doesn't
    if not os.path.exists(private_key_path) or not os.path.exists(public_key_path):
        logger.debug(f"SSH key pair not found. Generating new key pair: {key_name}")
        run_command(['ssh-keygen', '-t', 'rsa', '-b', '2048', '-f', private_key_path, '-N', '']) #, check=True)

    # Copy the public key to the guest mount
    guest_ssh_dir = os.path.join(guest_mount_path, 'root', '.ssh')
    guest_authorized_keys = os.path.join(guest_ssh_dir, 'authorized_keys')

    # Ensure the guest .ssh directory exists
    os.makedirs(guest_ssh_dir, exist_ok=True)

    # Append the public key to the authorized_keys file in the guest mount
    with open(public_key_path, 'r') as public_key_file:
        public_key = public_key_file.read()
        with open(guest_authorized_keys, 'a') as authorized_keys_file:
            authorized_keys_file.write(public_key + '\n')

    logger.debug(f"Public key {public_key_path} copied to {guest_authorized_keys}")

def stash_vm(conn, dst_path, vmname):
    def extract_disk_path_from_xml(xml_desc):
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml_desc)
        for disk in root.findall("./devices/disk[@device='disk']/source"):
            return disk.get('file')
        return None

    # Lookup the VM by name
    logger = logging.getLogger(__name__)
    logger.debug(f"Trying to stash {vmname} into {dst_path}")
    vm = conn.lookupByName(vmname)

    if vm is None:
        raise Exception(f"Failed to find VM with name {vmname}")

    # Get the XML description of the VM
    xml_desc = vm.XMLDesc(0)

    # Save the XML to the destination path
    xml_file_path = f"{dst_path}.xml"
    with open(xml_file_path, 'w') as xml_file:
        xml_file.write(xml_desc)

    # Extract the disk image path from the XML
    disk_path = extract_disk_path_from_xml(xml_desc)

    if disk_path is None:
        raise Exception("Failed to extract disk path from VM XML")

    # Copy the disk image to the destination path
    logger.debug(f"Stashing {dst_path} for later re-use. Reduce! Reuse! Recycle!")
    shutil.copy2(disk_path, dst_path)
        
def create_temp_inventory_file(hosts, group='servers'):
    """
    Create a temporary inventory file with the specified hosts in the specified group.

    Args:
        hosts (list): A list of hostnames to include in the inventory.
        group (str): The name of the group to which the hosts belong.

    Returns:
        str: The path to the temporary inventory file.
    """
    # Create a temporary file
    temp_file = tempfile.NamedTemporaryFile(mode='w', prefix='inventory.', suffix='.ini', delete=False)

    # Write the inventory content to the temporary file
    try:
        temp_file.write(f'[{group}]\n')
        for host in hosts:
            temp_file.write(f'{host} ansible_ssh_common_args="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"\n')
    finally:
        temp_file_path = temp_file.name
        temp_file.close()

    return temp_file_path


def check_images_directory(images):
    if not os.path.isdir(images):
        Fatal(f"Specified image directory {images} is not a valid directory.")
    os.makedirs(images + '/lustre/servers', exist_ok=True)
    os.makedirs(images + '/lustre/clients', exist_ok=True)

def restart_domain(conn, hname, restart_libvirt=False):
    logger = logging.getLogger(__name__)
    if restart_libvirt:
        logger.debug(f"Restarting libvirt")
        conn.restart() # restart libvirt so networking works
    logger.debug(f"Starting {hname}") 
    if not check_vm_status(conn, hname, shutdown=True, destroy=False):
        Fatal(f"Could not shutdown {hname}")
    dom = conn.lookupByName(hname)
    dom.create()

# returns 0, kernel on success
# returns 1, error string on failure
def get_kernel(hname):
    command = f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {hname} uname -r"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if result.returncode == 0:
        return(0, result.stdout.strip())
    else:
        return(1, result.stderr.strip())

def create_gold(conn, bootstrap_vm, hname, inventory_file, playbook_file, group, verbosity, ansible_log_prefix=None):

    if not check_vm_status(conn, bootstrap_vm):
        Fatal(f"VM {bootstrap_vm} does not exist or is not shut off.")

    if group not in [ 'clients', 'servers' ]:
        Fatal(f"Unknown group {group}")

    # clone the gold server and start it
    logger = logging.getLogger(__name__)
    logger.debug(f"Cloning {hname} from {bootstrap_vm}") 
    create_node(conn, bootstrap_vm, hname) 
    restart_domain(conn, hname, restart_libvirt=True)

    logger.debug(f"Running ansible playbook {playbook_file} on {hname}") 
    run_playbook(hname, inventory_file, playbook_file, group, verbosity, f"{ansible_log_prefix}.{hname}")

    # Execute the 'uname -r' command to get the kernel version
    (ret, output) = get_kernel(hname) 
    if ret == 0:
        logger.debug(f"Returning {output} as kernel version of {hname}")
        kernel_version = output
    else:
        kernel_version = None
        Fatal("Couldn't fetch kernel version from {hname}: {kernel_version}")

    shutdown_vm(conn, hname)

    return kernel_version

# weird function that we need so the ansible playbook output is plain text 
def strip_ansi_escape_codes(text):
    """Remove ANSI escape codes and reduce multiple newlines to a single newline in the text."""
    text = re.sub(r'\x1B(?:[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)
    return re.sub(r'\n+', '\n', text)

# weird function that we need so we can save ansible playbook output to a specified file
def event_handler_factory(output_file,filemode):
    """Factory function to create event handlers with a specific output file."""
    def event_handler(event_data):
        """Function to log the output of each Ansible event to a specified file."""
        if 'stdout' in event_data:
            logger = logging.getLogger(__name__)
            clean_output = strip_ansi_escape_codes(event_data['stdout'])
            if output_file:
                with open(output_file, filemode) as file:
                    file.write(clean_output + '\n')
            logger.info(clean_output)
    return event_handler

"""Prints a message to a file if a file pointer is provided."""
def summary(msg):
    logger = logging.getLogger(__name__)
    logger.warning(f"SUMMARY: {msg}") 

def run_playbook(hname, inventory_file, playbook_file, group, verbosity, output_prefix=None):
    logger = logging.getLogger(__name__)

    # get absolute paths
    playbook_file  = os.path.abspath(playbook_file)
    inventory_file = os.path.abspath(inventory_file)

    # turn off key checking
    os.environ['ANSIBLE_HOST_KEY_CHECKING'] = 'False'

    # set up the output file
    if output_prefix:
        output_filename = f"{output_prefix}.{playbook_file.split('/')[-1]}.out"
    else:
        output_filename = None

    # Construct the kwargs for ansible_runner.run
    filemode='w' # TODO: make this the same across the program
    kwargs = {
        "playbook":  playbook_file,
        "inventory": [ inventory_file ],
        "event_handler": event_handler_factory(output_filename,filemode),  
        "verbosity": verbosity,
        "quiet": False  # Ensure ansible_runner print to stdout as well
    }

    if hname is not None:
        temp_inventory = create_temp_inventory_file([hname], group=group)
        kwargs['inventory'].append(temp_inventory)
        kwargs["limit"] = hname

    # Run the playbook
    logger.debug(f"Running playbook {playbook_file}")
    result = ansible_runner.run(**kwargs)

    if result.status == 'successful':
        summary(f"Playbook {playbook_file} executed successfully. Output in {output_filename}.")
    else:
        Fatal(f"Playbook execution failed with status: {result.status}")

def get_first_storage_pool_info(conn):
    """
    Get the name and path of the first available storage pool.

    Args:
        conn (libvirt.virConnect): The libvirt connection object.

    Returns:
        tuple: A tuple containing the name and path of the first storage pool.
    """
    # Get the list of all storage pools
    pools = conn.listAllStoragePools()
    if not pools:
        raise Exception("No storage pools found")

    # Get the first storage pool
    pool = pools[0]

    # Get the XML description of the storage pool
    xml_desc = pool.XMLDesc(0)
    xml_root = ET.fromstring(xml_desc)

    # Extract the name and path from the XML
    name = pool.name()
    path_element = xml_root.find(".//path")
    if path_element is not None:
        path = path_element.text
    else:
        raise Exception("Path element not found in storage pool XML")

    return (name, path)

def find_gold_image(full_prefix):
    directory = os.path.dirname(full_prefix)
    base_prefix = os.path.basename(full_prefix)
    
    if not os.path.isdir(directory):
        Fatal(f"The directory '{directory}' does not exist or is not a directory.")
        return None

    # pattern to pull kernel version from all available images matching the prefix
    pattern = re.escape(base_prefix) + r'(\d+\.\d+\.\d+-\d+).*\.img$'
    latest_file = None
    latest_version = None

    # returns a tuple. If there are multiple matches, the tuple compare will do piece-wise correctly
    # for example, 4.18.0-547.el8.x86_64 will be "greater" than 4.18.0-536.el8.x86_64 because
    # 4 is the same, 18 is the same, 0 is the same, and finally 547 > 536
    def parse_kernel_version(version_str):
        parts = re.split(r'[\.-]', version_str)
        return tuple(int(part) if part.isdigit() else part for part in parts)

    for filename in os.listdir(directory):
        logger = logging.getLogger(__name__)
        #logger.debug(f"Checking possible gold image {filename}")
        match = re.match(pattern, filename)
        if match:
            version = parse_kernel_version(match.group(1))
            logger.debug(f"Found kernel version {version} in image {filename}")
            if latest_file is None or version > latest_version:
                latest_file = filename
                latest_version = version
        #else:
        #    logger.debug(f"No regex match found on {filename} using prefix {base_prefix}")

    return os.path.join(directory, latest_file) if latest_file else None

def get_gold_definitions(images,lversion,zversion):
    golds = {
        'clients': {
            'image_prefix': f"{images}/lustre/clients/Lustre-{lversion}.Patch-None.Kernel-",
            'image'       : None,
            'hname'       : 'gold-lustre-client'
        },
        'servers': {
            'image_prefix': f"{images}/lustre/servers/Lustre-{lversion}.ZFS-{zversion}.Patch-None.Kernel-",
            'image'       : None,
            'hname'       : 'gold-lustre-server'
        }
    }
    return golds

def make_gold_vms(conn,bootstrap_vm,images,inventory,inventory_file,playbook_file,rebuild_vms,rebuild_golds,verbosity, ansible_log_prefix):
    logger = logging.getLogger(__name__)
    lversion = get_inventory_value(inventory, 'all.vars.lustre.version')
    zversion = get_inventory_value(inventory, 'all.vars.zfs.version')
    logger.debug(f"Need gold server {lversion}.{zversion} and gold client {lversion}")

    # get the libvirt storage pool
    (pool_name, pool_path) = get_first_storage_pool_info(conn) 

    # initialize variables 
    golds = get_gold_definitions(images,lversion,zversion)

    for group,gold in golds.items(): 
        if not rebuild_vms and check_vm_status(conn, gold['hname'], shutdown=True, destroy=False):
            logger.debug(f"Reusing existing VM {gold['hname']}")
            continue

        if not check_vm_status(conn, gold['hname'], shutdown=True, destroy=True):
            Fatal(f"VM {gold['hname']} could not be destroyed.")
        
        gold['image'] = find_gold_image(gold['image_prefix'])
        if gold['image'] and not rebuild_golds:
            logger.debug(f"Restoring gold {gold['hname']} from stashed VM {gold['image']}")
            restore_vm_from_stash(conn, gold['image'], f"{gold['image']}.xml", pool_name, gold['hname'])
        else:
            if gold['image'] and os.path.exists(gold['image']):
                logger.debug(f"Rebuilding (and restashing) VM {gold['hname']} due to user request.")
            kernel_version = create_gold(conn, bootstrap_vm, gold['hname'], inventory_file, playbook_file, group, verbosity, ansible_log_prefix)
            gold['image'] = gold['image_prefix'] + kernel_version + '.img'
            stash_vm(conn, gold['image'], gold['hname'])

    return (golds['servers']['hname'], golds['clients']['hname']) 

def shutdown_vm(conn,hname):
    logger = logging.getLogger(__name__)
    dom = conn.lookupByName(hname)
    dom.shutdown()
    count = 0
    max_retries = 10
    sleep_time = 3
    while True:
        time.sleep(sleep_time)
        if dom.info()[0] == libvirt.VIR_DOMAIN_SHUTOFF:
            break
        if count < max_retries:
            logger.debug(f"Sleeping {count} of {max_retries} to wait for {hname} to shutdown")
            try:
                dom.shutdown()
            except libvirt.libvirtError as e:
                pass # probably a race condition and it's shutdown now
            count += 1
        else:
            logger.debug(f"Warning: difficulty shutting down {hname}. Will forcibly destroy. Might cause lost data.")
            try:
                dom.destroy()
            except libvirt.libvirtError as e:
                pass # probably a race condition and it's shutdown now
    logger.debug(f"Shutdown {hname}")

def check_vm_status(conn,vm_name,shutdown=True,destroy=False):
    # Define a custom error handler that does nothing
    def custom_error_handler(ctx, err):
            pass

    try:
        # Set a custom error handler bec we don't need an error msg if it doesn't exist
        # Hopefully no-one else previously set a custom error handler
        # we tried to fetch the current handler ourselves but libvirt doesn't seem to have a function for that
        libvirt.registerErrorHandler(custom_error_handler, None)
        dom = conn.lookupByName(vm_name)
    except libvirt.libvirtError:
        #logger.debug(f"VM {vm_name} does not exist.")
        return True if destroy else False
    finally:
        # Restore the default error handler
        libvirt.registerErrorHandler(None, None)

    # does the caller require it to be shutdown?
    if shutdown:
        # Check if the VM is running and stop it if so
        if dom.isActive():
            shutdown_vm(conn, vm_name)

    # does the caller require it to be destroyed?
    if destroy:
        logger = logging.getLogger(__name__)
        delete_vm_storage(conn, vm_name)
        # Undefine the VM, removing all associated storage and snapshots
        dom.undefineFlags(
            libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE |
            libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA |
            libvirt.VIR_DOMAIN_UNDEFINE_NVRAM |
            0)
        logger.debug(f"Successfully destroyed existing {vm_name}.")

    return True

def delete_vm_storage(conn, vm_name):
    """Delete storage volumes for a VM."""
    logger = logging.getLogger(__name__)
    try:
        dom = conn.lookupByName(vm_name)
        xml_desc = dom.XMLDesc(0)
        xml = ET.fromstring(xml_desc)

        # Iterate over all disk devices in the domain's XML
        for disk in xml.findall('devices/disk'):
            if disk.get('device') == 'disk':
                source = disk.find('source')
                if source is not None:
                    disk_path = source.get('file')
                    # Find the volume by path and delete it
                    try:
                        vol = conn.storageVolLookupByPath(disk_path)
                        vol.delete(0)  # 0 is the flags parameter, currently unused
                        logger.debug(f"Deleted volume: {disk_path}")
                    except libvirt.libvirtError as e:
                        logger.debug(f"Error deleting volume {disk_path}: {e}")

    except libvirt.libvirtError as e:
        logger.debug(f"Failed to find or access VM {vm_name} for storage deletion: {e}")

def check_network_exists(conn, network_name):
    logger = logging.getLogger(__name__)
    logger.debug(f"Checking existence of network {network_name}")
    """Check if the specified network exists."""
    try:
        conn.networkLookupByName(network_name)
        return True
    except libvirt.libvirtError:
        logger.debug(f"Network {network_name} does not exist")
        return False

def get_mac_address(conn, vm_name, network_name):
    logger = logging.getLogger(__name__)
    # Lookup the domain by name
    vm = conn.lookupByName(vm_name)
    if vm is None:
        Fatal(f"No VM found with the name: {vm_name}")
    
    # Get the XML description of the VM
    xml_desc = vm.XMLDesc(0)
    
    # Parse the XML to find the MAC address for the given network
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_desc)
    
    for interface in root.findall('.//interface'):
        source = interface.find('source')
        mac = interface.find('mac')
        if source is not None and mac is not None:
            if source.get('network') == network_name:
                mac = mac.get('address')
                logger.debug(f"Found MAC address {mac} for {vm_name} on network {network_name}")
                return mac
    
    logger.debug(f"MAC address not found for vm {vm_name} on network {network_name}")
    return None 

def setup_hostonly_network(conn, network, network_name, mac, ip, hostname):
    """
    Set up or update a host-only network with a single VM entry.
    
    Args:
        conn: Connection object to the libvirt API.
        network (str): The first three octets of the IP address for the network.
        network_name (str): The name of the network.
        mac (str): The MAC address for the VM.
        ip (str): The fourth octet of the IP address for the VM.
        hostname (str): The hostname for the VM.
    """
    network_xml = f"""
<network>
  <name>{network_name}</name>
  <bridge name='virbr1' stp='on' delay='0'/>
  <ip address='{network}.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='{network}.2' end='{network}.254'/>
    </dhcp>
  </ip>
</network>
"""

    def add_entry(network, hostname, mac, host_entry, description):
        logger = logging.getLogger(__name__)
        if mac is None:
            Fatal(f"Trying to add {hostname} to {network_name} but mac address is unknown.")
        logger.debug(f"Adding {hostname}:{mac} to {description} network {network_name}")
        network.update(3, 4, -1, host_entry, 3)
        #network.update(4, 0, 0, host_entry)

    if mac is None:
        mac = get_mac_address(conn, hostname, network_name)
    host_entry = f"<host mac='{mac}' name='{hostname}' ip='{network}.{ip}'/>"

    if check_network_exists(conn, network_name):
        if is_host_in_network_by_name(conn, network_name, hostname, ip):
            logger = logging.getLogger(__name__)
            logger.debug(f"Reusing existing entry for {hostname} in network {network_name}")
        else:
            vnetwork = conn.networkLookupByName(network_name)
            add_entry(vnetwork, hostname, mac, host_entry, 'existing')
    else:
        vnetwork = conn.networkDefineXML(network_xml)
        vnetwork.setAutostart(True)
        vnetwork.create()
        add_entry(vnetwork, hostname, mac, host_entry, 'newly_created')

def remove_network_if_exists(conn, network_name):
    """Remove the specified network if it exists."""
    if check_network_exists(conn, network_name):
        logger = logging.getLogger(__name__)
        logger.debug(f"Network '{network_name}' exists. Cleaning it up.")
        network = conn.networkLookupByName(network_name)
        network.destroy()
        network.undefine()

def clone_vm(bootstrap_vm, new_vm):
    """Clone a VM."""
    logger = logging.getLogger(__name__)
    logger.debug(f"Cloning {bootstrap_vm} to {new_vm}")
    clone_command = f"virt-clone --original {bootstrap_vm} --name {new_vm} --auto-clone --nonsparse"
    run_command(clone_command.split())

def add_nic_to_vm(conn, vm_name, network_name, mac_address=None):

    dom = conn.lookupByName(vm_name)
    xml_desc = dom.XMLDesc()
    root = ET.fromstring(xml_desc)
    devices = root.find('devices')

    # If no mac_address passed, create a new one
    if not mac_address:
        mac_address = "02:%s" % ":".join(["%02x" % (i,) for i in os.urandom(5)])
    
    interface = ET.SubElement(devices, 'interface', type='network')
    ET.SubElement(interface, 'mac', address=mac_address)
    ET.SubElement(interface, 'source', network=network_name)
    ET.SubElement(interface, 'model', type='virtio')
    conn.defineXML(ET.tostring(root).decode())

    return mac_address

def create_disk_image(image_path, size):
    """Create a raw disk image using qemu-img."""
    command = ["qemu-img", "create", "-f", "raw", image_path, size]
    logger = logging.getLogger(__name__)
    try:
        run_command(command)
        logger.debug(f"Disk image {image_path} created with size {size}.")
    except subprocess.CalledProcessError as e:
        Fatal(f"Failed to create disk image: {e}")

def attach_disk_to_vm(vm_name, disk_path, target_dev, cache_mode='none', persistent=True):
    """Attach a disk to a VM using virsh."""
    # there is some annoying thing described here https://stackoverflow.com/questions/14935953/kvm-virsh-attach-disk-does-not-honour-device-letter
    # apparently the target_dev argument is passed as a hint only to the guest which might use a different name
    # we need to know the actual name for subsequent mounting so the --serial will force a predefined name in /dev/disk/by-id/ which is a symlink to dev
    command = ["virsh", "attach-disk", vm_name, disk_path, target_dev, "--cache", cache_mode, "--serial", target_dev]
    if persistent:
        command.append("--persistent")
    logger = logging.getLogger(__name__)
    try:
        run_command(command)
        logger.debug(f"Disk {disk_path} attached to {vm_name} as {target_dev}.")
    except subprocess.CalledProcessError as e:
        Fatal(f"Failed to attach disk to VM: {e}")

def get_image_storage_pool_path(conn):
    """Get the path of the default storage pool."""
    logger = logging.getLogger(__name__)
    try:
        # Get the default storage pool (usually named 'default')
        pool = conn.storagePoolLookupByName('images')
        # Get the XML description of the pool
        pool_xml = pool.XMLDesc(0)
        # Parse the XML to find the path
        path_start = pool_xml.find('<path>') + 6  # Add 6 to skip the <path> tag itself
        path_end = pool_xml.find('</path>', path_start)
        path = pool_xml[path_start:path_end]
        return path
    except libvirt.libvirtError as e:
        logger.debug(f"Error getting default storage pool path: {e}")
        return None

def set_hostname_keypair_selinux_lustre_options(conn, vm_name, selinux):
    logger = logging.getLogger(__name__)
    try:
        dom = conn.lookupByName(vm_name)
    except libvirt.libvirtError:
        Fatal(f"VM {vm_name} not found")

    mpoint = f"/tmp/mnt/vm_disk.{os.getpid()}"
    os.makedirs(mpoint, exist_ok=True)

    try:
        vmimage = subprocess.check_output(['virsh', 'domblklist', vm_name, '--details']).decode()
        for line in vmimage.splitlines():
            if 'vda' in line:
                vmimage = line.split()[-1]
                break
        else:
            raise Exception("vda not found in domblklist output")

        run_command(['guestmount', '-a', vmimage, '-i', mpoint])
        hfile = os.path.join(mpoint, 'etc/hostname')
        if not os.path.exists(hfile):
            raise Exception(f"Warning: {hfile} not found")

        # set hostname
        with open(hfile, 'w') as f:
            f.write(vm_name + '\n')

        # Update SELinux configuration
        sfile = os.path.join(mpoint, 'etc/selinux/config')
        if not os.path.exists(sfile):
            raise Exception(f"Warning: {sfile} not found")
        with open(sfile, 'r') as f:
            lines = f.readlines()
        with open(sfile, 'w') as f:
            for line in lines:
                if line.startswith('SELINUX='):
                    f.write(f'SELINUX={selinux}\n')
                else:
                    f.write(line)

        # disable the firewall
        firewalld_service = os.path.join(mpoint, 'etc/systemd/system/firewalld.service')
        if os.path.lexists(firewalld_service):
            os.remove(firewalld_service)
        os.symlink('/dev/null', firewalld_service)

        setup_ssh_key_and_copy_to_guest(mpoint)

        # unmount the disk image
        run_command(['guestunmount', mpoint]) 
        logger.debug(f"Set hostname to be {vm_name}")

    except Exception as e:
        Fatal(e)

def is_host_in_network_by_name(conn, network_name, host_name, expected_ip):
    """
    Check if a host with the given name is already in the network with the expected IP address.
    
    :param conn: libvirt connection object
    :param network_name: Name of the network
    :param host_name: Name of the host to check
    :param expected_ip: Expected IP address of the host
    :return: True if the host is in the network with the expected IP, False otherwise
    """
    logger = logging.getLogger(__name__)
    try:
        network = conn.networkLookupByName(network_name)
        xml_desc = network.XMLDesc()
        root = ET.fromstring(xml_desc)
        dhcp_section = root.find(".//dhcp")

        if dhcp_section is not None:
            for host in dhcp_section.findall("host"):
                if host.get("name") == host_name:
                    last_octet = int(host.get("ip").split('.')[-1])
                    if last_octet != expected_ip:
                        logger.debug(f"WARN: {host_name} exists but last octet of IP {expected_ip} != {last_octet} from {host.get('ip')}")
                        return False
                    else:
                        return True
        return False

    except libvirt.libvirtError as e:
        logger.debug(f"Error: {e}")
        return False

def remove_ssh_host_keys(hostname):
    def actual_remove(hostname, path, owner_uid, owner_gid):
        logger = logging.getLogger(__name__)
        logger.debug(f"Removing ssh key for {hostname} from {path}")
        run_command(["ssh-keygen", "-f", path, "-R", hostname])
        # Reset file ownership to the original user
        os.chown(path, owner_uid, owner_gid)

    # Check if the script is running as root
    is_root = os.getuid() == 0

    # If running as root, check if it's a sudo session
    sudo_user = os.environ.get('SUDO_USER')

    # Determine the known_hosts file path for the current user (root or non-root)
    current_user_known_hosts = os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")

    # Get the current user's UID and GID for ownership resetting
    current_user_uid = os.getuid()
    current_user_gid = os.getgid()

    # Remove the host key for the current user (root or non-root) and reset ownership
    actual_remove(hostname, current_user_known_hosts, current_user_uid, current_user_gid)

    # If running as root in a sudo session, also remove the host key for the original user
    if is_root and sudo_user:
        original_user_home = os.path.expanduser(f"~{sudo_user}")
        original_user_known_hosts = os.path.join(original_user_home, ".ssh", "known_hosts")
        # Get the original user's UID and GID
        original_user_uid = os.stat(original_user_home).st_uid
        original_user_gid = os.stat(original_user_home).st_gid
        actual_remove(hostname, original_user_known_hosts, original_user_uid, original_user_gid)

# Function to execute a command in the VM. Return the output.
def execute_command_in_vm(comm,hname,command):
    try:
        # Open a session to the VM
        domain = conn.lookupByName(hname)
        session = domain.openConsole()
        # Execute the command
        session.send(command + "\n")
        # Read the output
        output = ""
        while True:
            data = session.recv(1024)
            if not data:
                break
            output += data.decode('utf-8')
        return output
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.debug(f"Error executing command in VM: {e}", file=sys.stderr)
        return None

def create_node(conn, src_vm, target_vm, network_name=None, network=None, target_ip=None, hds=None, use_existing=False):
    logger = logging.getLogger(__name__)
    logger.debug(f"ESTABLISHING {target_vm} with target ip of {target_ip} and hds {hds}")
    if not check_vm_status(conn, src_vm, shutdown=True, destroy=False):
        Fatal(f"Warning: VM {src_vm} is not appropriately shutdown.")
    if use_existing and check_vm_status(conn, target_vm, shutdown=True, destroy=False):
        logger.debug(f"Reusing existing VM {target_vm}")
        mac_address = None
    else:
        if not check_vm_status(conn, target_vm, shutdown=True, destroy=True):
            logger.debug(f"Warning: VM {target_vm} could not be cleaned up.")

        # Clone the base VM
        clone_vm(src_vm, target_vm)

        set_hostname_keypair_selinux_lustre_options(conn,target_vm, 'disabled')

        if hds:
            # this get_letter thing is just a way to iterate through the alphabet to create good HDD names
            get_letter = lambda x: chr(ord('b') + x )
            for idx,hd in enumerate(hds):
                path = f"{get_image_storage_pool_path(conn)}/{target_vm}_hdd{idx}_{hd}GB"
                create_disk_image(path, f"{hd}G")
                attach_disk_to_vm(target_vm, path, f"sd{get_letter(idx)}")

        # Add NIC to the cloned VM
        if target_ip:
            mac_address = add_nic_to_vm(conn, target_vm, network_name)

    # give static IP assignment of the new VM to the network
    if target_ip:
        setup_hostonly_network(conn, network, network_name, mac_address, target_ip, target_vm)

    # clean up ssh known_hosts for easier ssh communication after creation
    remove_ssh_host_keys(target_vm)

def extract_host_details(d, target_groups, current_group=None, host_details = None):
    if host_details is None:
        host_details = {}

    if isinstance(d, dict):
        for key, value in d.items():
            if key == 'hosts':
                for host, attributes in value.items():
                    host_details[host] = attributes
                    if current_group:
                        host_details[host]['group'] = current_group
            elif key in target_groups:
                host_details = extract_host_details(value, target_groups, key, host_details)
            else:
                host_details = extract_host_details(value, target_groups, current_group, host_details)
    return host_details

def load_yaml(file):
    # helper function to add inheritance here manually since ansible does this for us
    def apply_group_vars_to_hosts(inventory, parent_vars=None):
        #logger.debug(f"Manually applying inheritance in the yaml inventory file")
        logger = logging.getLogger(__name__)
        for group_name, group_info in inventory.items():
            logger.debug(f"Processing group: {group_name}")
            group_vars = group_info.get('vars', {}).copy()
            if parent_vars:
                group_vars.update(parent_vars)
            if 'hosts' in group_info:
                for host_name, host_info in group_info['hosts'].items():
                    host_info.update(group_vars)
            if 'children' in group_info:
                apply_group_vars_to_hosts(group_info['children'], group_vars)

    logger = logging.getLogger(__name__)
    logger.debug(f"Parsing inventory file {file}")
    with open(file, 'r') as f:
        inventory = yaml.safe_load(f) 

    # add inheritance here manually since ansible does this for us
    apply_group_vars_to_hosts(inventory)
    return inventory

def Fatal(msg):
    logger = logging.getLogger(__name__)
    logger.error(f"FATAL ERROR: {msg}")
    sys.exit(-1)

def get_inventory_value(inventory, key, required=True):
    try:
        value = inventory
        for k in key.split('.'):
            value = value[k]
        return value
    except KeyError:
        if required:
            Fatal(f"Missing '{key}' in the inventory file.")
        else:
            pass

def get_hosts(inventory, group):
    hosts = set()

    def recurse(dictionary, target_group, is_target_group):
        if 'hosts' in dictionary and is_target_group:
            hosts.update(dictionary['hosts'].keys())

        for key, value in dictionary.items():
            if key != 'hosts' and isinstance(value, dict):
                recurse(value, target_group, is_target_group or key == target_group)

    recurse(inventory['all'], group, False)
    return hosts

def restart_hosts(conn, hosts):
    logger = logging.getLogger(__name__)
    # Start the cloned VMs
    for hname in hosts:
        logger.debug(f"Starting {hname},")
        dom = conn.lookupByName(hname)
        dom.create()
    time.sleep(10)

    # TODO: we just started them a second ago, necessary to restart them here? 
    # therefore this reboot here is probably unnecessary
    for hname in hosts:
        restart_domain(conn, hname)
    time.sleep(10)

def die_unless_root():
    # Check if script is run as root
    if os.geteuid() != 0:
        Fatal("Must be run as root")

def show_resources(conn, args, inventory, vm_dir, hosts):
    logger = logging.getLogger(__name__)
    avail = check_vm_status(conn, args.boot_vm_name, shutdown=False, destroy=False)
    logger.debug(f"Bootstrap VM {args.boot_vm_name} {'is' if avail else 'is not'} available for re-use to create gold images if needed.")
    avail = check_network_exists(conn, args.virt_network)
    logger.debug(f"Network '{args.virt_network}' {'is' if avail else 'is not'} available for re-use.")

    lversion = get_inventory_value(inventory, 'all.vars.lustre.version')
    zversion = get_inventory_value(inventory, 'all.vars.zfs.version')
    golds = get_gold_definitions(vm_dir, lversion, zversion)
    for group,gold in golds.items(): 
        pattern = f"{gold['image_prefix']}*.img"
        for f in glob.glob(pattern):
            logger.debug(f"{f.split('/')[-1]} is available to create gold VM for {group}")
        avail = check_vm_status(conn, gold['hname'], shutdown=False, destroy=False)
        logger.debug(f"Gold VM {gold['hname']} {'is' if avail else 'is not'} available for re-use to create {group} if needed.")

    for host in hosts:
        avail = check_vm_status(conn, host, shutdown=False, destroy=False)
        logger.debug(f"Host VM {host} {'is' if avail else 'is not'} available for re-use to create cluster if needed.")


# helper function to make sure we rebuild only what is necessary
def build_needed(conn, resource, user_overrides, Type):
    logger = logging.getLogger(__name__)
    if user_overrides and (Type in user_overrides or 'all' in user_overrides):
        logger.debug(f"Need to build {resource} because of user specification")
        return True

    if Type in ['bootstrap', 'vms', 'golds']:
        avail = check_vm_status(conn, resource, shutdown=False, destroy=False)
        if not avail:
            logger.debug(f"Need to build initial resource {resource}")
            return True
    elif Type == 'network':
        avail = check_network_exists(conn, resource)
        if not avail:
            logger.debug(f"Need to build initial resource {resource}")
            return True
    else:
        Fatal(f"Illegal resource type {Type}")

    logger.debug(f"Resource {resource} does not require a rebuild")
    return False

# allow user to set all variable values in the inventory file
def override_args_from_inventory(args, inventory):
    logger = logging.getLogger(__name__)
    # Loop over each attribute in args
    for arg_name in vars(args):
        # Build the expected YAML path
        inventory_path = f'all.vars.{arg_name}'

        # Attempt to get a value from the inventory
        new_value = get_inventory_value(inventory=inventory, key=inventory_path, required=False)
        if new_value is not None:
            current_value = getattr(args, arg_name)
            if current_value != new_value:
                setattr(args, arg_name, new_value)
                logger.debug(f"Overriding {arg_name} from {current_value} to {new_value}")
    
    return args  # Returning the modified args for clarity

def execute_script(script_path, output_file=None):
    filemode='w' # TODO: make this the same across the program
    try:
        # Execute the script and capture the output
        logger = logging.getLogger(__name__)
        logger.info(f"Running test script {script_path}") 
        result = subprocess.run([script_path], check=True, capture_output=True, text=True)
        
        # Print and possibly save the output
        if output_file:
            with open(output_file, filemode) as file:
                file.write(result.stdout)
        summary(f"Executed {script_path}: {result.returncode}. Output in {output_file}.")
        return result.returncode  # Return the return code of the script
    except subprocess.CalledProcessError as e:
        # Print the error message to STDOUT and handle the error output
        logger = logging.getLogger(__name__)
        logger.error(f"Error executing script: {e}\n{e.output}")
        if output_file:
            with open(output_file, filemode) as file:
                file.write(e.output)
        return e.returncode
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error executing script: {e}")
        return -1

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='''Create libvirt VMs, install, configure, mount, test a Lustre cluster. Defaults to reuse resources and run all playbooks.
                       Use --rebuilt and --skip to override.''',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter  # Add this line
    )
    parser.add_argument('-b', '--boot_vm_name',             default='bootstrap',                    help='Name of the base VM.')
    parser.add_argument('-i', '--ansible_playbook_install', default='./ansible/install_all.yaml',   help='Name of the ansible install playbook')
    parser.add_argument('-c', '--ansible_playbook_config',  default='./ansible/configure_all.yaml', help='Name of the ansible configure playbook')
    parser.add_argument('-t', '--ansible_playbook_test',    default='./ansible/test_lustre.yaml',   help='Name of the ansible test playbook')
    parser.add_argument('-v', '--ansible_verbosity',        default=0, type=int,                    help='Ansible verbosity')
    parser.add_argument('-T', '--test_script',              default=None, type=str,                 help='Test script to run after ansible test playbook')
    parser.add_argument('-o', '--output_dir',               default='./output', type=str,           help='Directory into which to store the output files')
    parser.add_argument('-n', '--virt_network',             default='hostonly-net',                 help='Name of virtual network to use/create')
    parser.add_argument('--rebuild', action='append', choices=['bootstrap', 'network', 'golds', 'vms', 'all'],    
                                                                                             help='Rebuild specified items (instead of re-using) if they exist')
    parser.add_argument('--skip',    action='append',   choices=['config', 'test'],          help='Skip specified steps (can be used multiple times)')
    parser.add_argument('--show',    action='store_true',                                    help='Show available resources which can be re-used and then quit')
    parser.add_argument('inventory_file',                         type=str,                  help='Path to the ansible inventory file')
    args = parser.parse_args()

    die_unless_root()

    # open the ansible inventory file and pull key items
    inventory = load_yaml(args.inventory_file)
    args      = override_args_from_inventory(args, inventory)
    hosts     = extract_host_details(inventory, ['clients', 'servers'])
    network   = get_inventory_value(inventory, 'all.vars.network')
    vm_dir    = get_inventory_value(inventory, 'all.vars.vm_dir')
    network['name'] = args.virt_network # define it here because we use it elsewhere

    # setup the paths for the various output files
    output_base = f"{args.output_dir.split('/')[-1]}/{args.inventory_file.split('/')[-1]}"
    os.makedirs(output_base, exist_ok=True)
    verbose_log        = f"{output_base}/log.all"
    summary_log        = f"{output_base}/log.summary"
    test_output        = f"{output_base}/{args.test_script.split('/')[-1]}.out"
    ansible_log_prefix = f"{output_base}/ansible"

    # setup the logging
    setup_logging(verbose_log,summary_log)
    logger = logging.getLogger(__name__)
    logger.debug(f"Running with {' '.join(sys.argv)}")

    # check that the various directories and the ansible playbooks exist 
    check_images_directory(vm_dir)
    for arg_name in [arg_name for arg_name in vars(args) if 'ansible_playbook' in arg_name or arg_name == 'test_script']:
        playbook_path = get_inventory_value(inventory, f"all.vars.{arg_name}", required=True)
        if not os.path.exists(playbook_path):
            Fatal(f"Ansible playbook {arg_name} at specified path {playbook_path} does not exist")

    # Example logger usage
    # logger.debug("This will appear only in verbose.log")
    # logger.info("This will also appear only in verbose.log")
    # logger.warning("This will appear in both verbose.log and concise.log")
    # logger.error("This will appear in both logs as well")

    # Connect to libvirt
    with LibvirtConnection() as conn:

        if args.show:
            show_resources(conn, args, inventory, vm_dir, hosts)
            sys.exit(0)

        # create the initial bootstrap VM if needed 
        if build_needed(conn, args.boot_vm_name, args.rebuild, 'bootstrap'):
            if not check_vm_status(conn, args.boot_vm_name, shutdown=True, destroy=True):
                Fatal(f"VM {gold['hname']} could not be destroyed.")
            install_initial_vm(conn, args.boot_vm_name, inventory, args.ansible_verbosity)

        # ensure the bootstrap VM is ready 
        if not check_vm_status(conn, args.boot_vm_name):
            Fatal(f"VM {args.boot_vm_name} does not exist or is not shut off.")

        if build_needed(conn, args.virt_network, args.rebuild, 'network'):
            remove_network_if_exists(conn, args.virt_network)

        # make or fetch the gold image for the servers and clients
        rebuilds = {}
        for resource in [ 'vms', 'golds' ]:
            if args.rebuild and ( resource in args.rebuild or 'all' in args.rebuild ):
                rebuilds[resource] = True
            else:
                rebuilds[resource] = False 
        gold_vms = {}
        (gold_vms['servers'], gold_vms['clients']) = make_gold_vms(
            conn = conn, 
            bootstrap_vm = args.boot_vm_name, 
            images = vm_dir, 
            inventory = inventory, 
            inventory_file = args.inventory_file, 
            playbook_file = args.ansible_playbook_install, 
            rebuild_vms = rebuilds['vms'],
            rebuild_golds = rebuilds['golds'],
            verbosity = args.ansible_verbosity,
            ansible_log_prefix = ansible_log_prefix)

        # now clone the base image for each requested lustre node
        if args.rebuild and ( 'vms' in args.rebuild or 'all' in args.rebuild ):
            use_existing = False
        else:
            use_existing = True
        for hname,hinfo in hosts.items():
            hip = hinfo['ip']
            hds = hinfo['hds']
            gvm = gold_vms[hinfo['group']]
            create_node(conn, gvm, hname, network['name'], network['addr'], hip, hds, use_existing)
            logger.debug(f"Created {hname}:{network['addr']}.{hip} from {gvm}.")

        # Restart libvirt services to apply changes
        conn.restart()

        # reboot the freshly coned VMs to make sure changes are applied appropriately
        restart_hosts(conn, hosts)

        # configure the lustre system
        if args.skip is not None and 'config' in args.skip:
            logger.debug(f"Skipping config as requested")
        else:
            run_playbook(None, args.inventory_file, args.ansible_playbook_config, None, args.ansible_verbosity, ansible_log_prefix)

        # test the lustre system
        if args.skip is not None and 'config' in args.skip:
            logger.debug(f"Skipping testing as requested")
        else:
            run_playbook(None, args.inventory_file, args.ansible_playbook_test, None, args.ansible_verbosity, ansible_log_prefix)
        
        if args.test_script:
            ret = execute_script(args.test_script, test_output)
            logger.info(f"Executed test script {args.test_script}: {ret}")
        else:
            logger.info(f"No test script specified.")

    logger.debug(f"Setup completed. Lustre cluster should now be running with new NICs attached to {network['name']}.")

if __name__ == "__main__":
    main()


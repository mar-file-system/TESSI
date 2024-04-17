#! /usr/bin/env python3.8

import ansible_runner
import argparse
import glob
import inspect
import libvirt
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

from pprint import pprint
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
            self.conn.close()
            time.sleep(5)
            print("Restarting libvirt network")
            subprocess.run(["systemctl", "restart", "virtlogd.socket"])
            subprocess.run(["systemctl", "restart", "libvirtd"])
            time.sleep(5)
            self._connect()

    def _connect(self):
        self.conn = libvirt.open(self.uri)
        if self.conn is None:
            print(f"Failed to open connection to {self.uri}")
            sys.exit(1)

    def __getattr__(self, name):
        # Forward attribute accesses to the underlying conn object
        return getattr(self.conn, name)

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
        print(f"Using ansible playbook {temp_playbook_path} to wait up to {timeout} seconds for {host} to boot.")
        # Run the playbook
        r = ansible_runner.run(
            playbook=temp_playbook_path,
            inventory=f'{host},',  # Comma is needed for a single host
        )
        if r.status == 'successful':
            print(f"SSH is available on {host}.")
            return True
        else:
            print(f"Failed to connect to {host} via SSH.")
            return False
    finally:
        # Clean up the temporary playbook file
        os.remove(temp_playbook_path)
        pass

def create_kickstart_file(hostname, ks_dir, ks_file, baseos_location, root_password, ssh_pub):
    os.makedirs(ks_dir, exist_ok=True)
    print(f"Creating kickstart file {ks_dir}/{ks_file}")
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
    print(f"Creating VM {hostname} from {baseos_location}")
    print(f"{command}")
    start_time = time.time()
    result = subprocess.run(command, shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        error_message = f"Warning message: Potential failure to create VM {hostname}:\n" \
                        f"Return code: {result.returncode}\n" \
                        f"Standard Output: {result.stdout.strip()}\n" \
                        f"Standard Error: {result.stderr.strip()}"
    elapsed = time.time() - start_time

    # Restart the VM and wait for it
    print(f"Created VM {hostname} in {elapsed} seconds. Will now restart it.")
    restart_domain(conn, hostname)
    wait_for_ssh_with_ansible(hostname, ansible_verbosity)

    # Clear out any old hostnames
    print(f"Removing any old ssh hostname entries for {hostname}")
    subprocess.run(["ssh-keygen", "-R", hostname])

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
    print(f"\tRestoring VM {vmname} from stashed configuration {src_path}")

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

    print(f"\tRestored VM {vmname} from stashed configuration")

def setup_ssh_key_and_copy_to_guest(guest_mount_path, key_name="id_rsa"):
    """
    Checks for an SSH key pair in $HOME/.ssh, creates one if it doesn't exist,
    and then copies the public key into the specified guest mount directory.

    Args:
        guest_mount_path (str): The path to the guest mount directory.
        key_name (str): The name of the SSH key pair (default: "id_rsa").
    """
    ssh_dir = os.path.join(os.environ['HOME'], '.ssh')
    private_key_path = os.path.join(ssh_dir, key_name)
    public_key_path = private_key_path + '.pub'

    # Check if the SSH key pair exists, create if it doesn't
    if not os.path.exists(private_key_path) or not os.path.exists(public_key_path):
        print(f"SSH key pair not found. Generating new key pair: {key_name}")
        subprocess.run(['ssh-keygen', '-t', 'rsa', '-b', '2048', '-f', private_key_path, '-N', ''], check=True)

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

    print(f"Public key {public_key_path} copied to {guest_authorized_keys}")

def stash_vm(conn, dst_path, vmname):
    def extract_disk_path_from_xml(xml_desc):
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml_desc)
        for disk in root.findall("./devices/disk[@device='disk']/source"):
            return disk.get('file')
        return None

    # Lookup the VM by name
    print(f"Trying to stash {vmname} into {dst_path}")
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
    print(f"\tStashing {dst_path} for later re-use. Reduce! Reuse! Recycle!")
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
    if restart_libvirt:
        print(f"\tRestarting libvirt")
        conn.restart() # restart libvirt so networking works
    print(f"\tStarting {hname}") 
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


def create_gold(conn, bootstrap_vm, hname, inventory_file, playbook_file, group, verbosity):

    if not check_vm_status(conn, bootstrap_vm):
        Fatal(f"VM {bootstrap_vm} does not exist or is not shut off.")

    if group not in [ 'clients', 'servers' ]:
        Fatal(f"Unknown group {group}")

    # clone the gold server and start it
    print(f"\tCloning {hname} from {bootstrap_vm}") 
    create_node(conn, bootstrap_vm, hname) 
    restart_domain(conn, hname, restart_libvirt=True)

    print(f"\tRunning ansible playbook {playbook_file} on {hname}") 
    run_playbook(hname, inventory_file, playbook_file, group, verbosity)

    # Execute the 'uname -r' command to get the kernel version
    (ret, output) = get_kernel(hname) 
    if ret == 0:
        print(f"Returning {output} as kernel version of {hname}")
        kernel_version = output
    else:
        kernel_version = None
        Fatal("Couldn't fetch kernel version from {hname}: {kernel_version}")

    # shut it down
    dom = conn.lookupByName(hname)
    dom.destroy()

    return kernel_version

def run_playbook(hname, inventory_file, playbook_file, group, verbosity):

    # get absolute paths
    playbook_file  = os.path.abspath(playbook_file)
    inventory_file = os.path.abspath(inventory_file)

    # turn off key checking
    os.environ['ANSIBLE_HOST_KEY_CHECKING'] = 'False'

    # Construct the kwargs for ansible_runner.run
    kwargs = {
        "playbook":  playbook_file,
        "inventory": [ inventory_file ],
        "verbosity": verbosity,
    }

    if hname is not None:
        temp_inventory = create_temp_inventory_file([hname], group=group)
        kwargs['inventory'].append(temp_inventory)
        kwargs["limit"] = hname

    # Run the playbook
    result = ansible_runner.run(**kwargs)

    if result.status == 'successful':
        print("Playbook executed successfully.")
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
        #print(f"\tChecking possible gold image {filename}")
        match = re.match(pattern, filename)
        if match:
            version = parse_kernel_version(match.group(1))
            print(f"\tFound kernel version {version} in image {filename}")
            if latest_file is None or version > latest_version:
                latest_file = filename
                latest_version = version
        #else:
        #    print(f"No regex match found on {filename} using prefix {base_prefix}")

    return os.path.join(directory, latest_file) if latest_file else None

def get_gold_definitions(images,lversion,zversion):
    golds = {
        'servers': {
            'image_prefix': f"{images}/lustre/servers/Lustre-{lversion}.ZFS-{zversion}.Patch-None.Kernel-",
            'image'       : None,
            'hname'       : 'gold-lustre-server'
        },
        'clients': {
            'image_prefix': f"{images}/lustre/clients/Lustre-{lversion}.Patch-None.Kernel-",
            'image'       : None,
            'hname'       : 'gold-lustre-client'
        }
    }
    return golds

def make_gold_vms(conn,bootstrap_vm,images,inventory,inventory_file,playbook_file,rebuild_vms,rebuild_golds,verbosity):
    lversion = get_inventory_value(inventory, 'all.vars.lustre.version')
    zversion = get_inventory_value(inventory, 'all.vars.zfs.version')
    print(f"Need gold server {lversion}.{zversion} and gold client {lversion}")

    # get the libvirt storage pool
    (pool_name, pool_path) = get_first_storage_pool_info(conn) 

    # initialize variables 
    golds = get_gold_definitions(images,lversion,zversion)

    for group,gold in golds.items(): 
        if not rebuild_vms and check_vm_status(conn, gold['hname'], shutdown=True, destroy=False):
            print(f"\tReusing existing VM {gold['hname']}")
            continue

        if not check_vm_status(conn, gold['hname'], shutdown=True, destroy=True):
            Fatal(f"VM {gold['hname']} could not be destroyed.")
        
        gold['image'] = find_gold_image(gold['image_prefix'])
        if gold['image'] and not rebuild_golds:
            print(f"\tRestoring gold {gold['hname']} from stashed VM {gold['image']}")
            restore_vm_from_stash(conn, gold['image'], f"{gold['image']}.xml", pool_name, gold['hname'])
        else:
            if gold['image'] and os.path.exists(gold['image']):
                print(f"\tRebuilding (and restashing) VM {gold['hname']} due to user request.")
            kernel_version = create_gold(conn, bootstrap_vm, gold['hname'], inventory_file, playbook_file, group, verbosity)
            gold['image'] = gold['image_prefix'] + kernel_version + '.img'
            stash_vm(conn, gold['image'], gold['hname'])

    return (golds['servers']['hname'], golds['clients']['hname']) 

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
        #print(f"\tVM {vm_name} does not exist.")
        return True if destroy else False
    finally:
        # Restore the default error handler
        libvirt.registerErrorHandler(None, None)

    # does the caller require it to be shutdown?
    if shutdown:
        # Check if the VM is running and stop it if so
        if dom.isActive():
            dom.destroy()  # This forcibly stops the domain
            print(f"\tVM {vm_name} was running. Stopped it.")

    # does the caller require it to be destroyed?
    if destroy:
        delete_vm_storage(conn, vm_name)
        # Undefine the VM, removing all associated storage and snapshots
        dom.undefineFlags(
            libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE |
            libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA |
            libvirt.VIR_DOMAIN_UNDEFINE_NVRAM |
            0)
        print(f"\tSuccessfully destroyed existing {vm_name}.")

    return True

def delete_vm_storage(conn, vm_name):
    """Delete storage volumes for a VM."""
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
                        print(f"\tDeleted volume: {disk_path}")
                    except libvirt.libvirtError as e:
                        print(f"\tError deleting volume {disk_path}: {e}")

    except libvirt.libvirtError as e:
        print(f"\tFailed to find or access VM {vm_name} for storage deletion: {e}")

def check_network_exists(conn, network_name):
    print(f"Checking existence of network {network_name}")
    """Check if the specified network exists."""
    try:
        conn.networkLookupByName(network_name)
        return True
    except libvirt.libvirtError:
        print(f"Network {network_name} does not exist")
        return False

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

    """
    # TODO : remove this unused function
    def add_entry_manually(network_name, hostname, mac, ip, description):
        if mac is None:
            Fatal(f"Trying to add {hostname} to {network_name} but mac address is unknown.")
        print(f"\tAdding {hostname} to {description} network {network_name}")
        host_entry = f"<host mac='{mac}' name='{hostname}' ip='{ip}' />"
        command = ["virsh", "net-update", network_name, "add", "ip-dhcp-host", host_entry, "--live", "--config"]
        subprocess_tabinated(command)
    """

    def add_entry(network, hostname, mac, host_entry, description):
        if mac is None:
            Fatal(f"Trying to add {hostname} to {network_name} but mac address is unknown.")
        print(f"\tAdding {hostname} to {description} network {network_name}")
        network.update(3, 4, -1, host_entry, 3)
        #network.update(4, 0, 0, host_entry)

    host_entry = f"<host mac='{mac}' name='{hostname}' ip='{network}.{ip}'/>"

    if check_network_exists(conn, network_name):
        if is_host_in_network_by_name(conn, network_name, hostname, ip):
            print(f"\tReusing existing entry for {hostname} in network {network_name}")
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
        print(f"Network '{network_name}' exists. Cleaning it up.")
        network = conn.networkLookupByName(network_name)
        network.destroy()
        network.undefine()

def subprocess_tabinated(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command, output=stdout, stderr=stderr)

    # add tabs and remove double newliens
    output = '\t' + stdout.replace('\n', '\n\t')
    output = output.replace('\n\t\n\t', '\n\t')
    output = output.replace('\n\n', '\n')
    output = output.replace('\t\n\t', '\t')

    # the clone output does some curses stuff which results in repeated lines. So clean that up here.
    lines = output.split('\n')
    alloc_lines = [i for i, line in enumerate(lines) if 'Allocating' in line]
    if alloc_lines:
        last_alloc_index = alloc_lines[-1]
        output = '\n'.join([line for i, line in enumerate(lines) if 'Allocating' not in line or i == last_alloc_index])

    print(output, end='')

def clone_vm(bootstrap_vm, new_vm):
    """Clone a VM."""
    clone_command = f"virt-clone --original {bootstrap_vm} --name {new_vm} --auto-clone --nonsparse"
    subprocess_tabinated(clone_command.split())

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
    try:
        subprocess_tabinated(command)
        print(f"\tDisk image {image_path} created with size {size}.")
    except subprocess.CalledProcessError as e:
        print(f"\tFailed to create disk image: {e}")
        sys.exit(1)

def attach_disk_to_vm(vm_name, disk_path, target_dev, cache_mode='none', persistent=True):
    """Attach a disk to a VM using virsh."""
    # there is some annoying thing described here https://stackoverflow.com/questions/14935953/kvm-virsh-attach-disk-does-not-honour-device-letter
    # apparently the target_dev argument is passed as a hint only to the guest which might use a different name
    # we need to know the actual name for subsequent mounting so the --serial will force a predefined name in /dev/disk/by-id/ which is a symlink to dev
    command = ["virsh", "attach-disk", vm_name, disk_path, target_dev, "--cache", cache_mode, "--serial", target_dev]
    if persistent:
        command.append("--persistent")
    try:
        subprocess_tabinated(command)
        print(f"\tDisk {disk_path} attached to {vm_name} as {target_dev}.")
    except subprocess.CalledProcessError as e:
        print(f"\tFailed to attach disk to VM: {e}")
        sys.exit(1)

def get_image_storage_pool_path(conn):
    """Get the path of the default storage pool."""
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
        print(f"Error getting default storage pool path: {e}")
        return None

def set_hostname_keypair_selinux_lustre_options(conn, vm_name, selinux):
    try:
        dom = conn.lookupByName(vm_name)
    except libvirt.libvirtError:
        print(f"VM {vm_name} not found")
        sys.exit(1)

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

        subprocess_tabinated(['guestmount', '-a', vmimage, '-i', mpoint])
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
        subprocess_tabinated(['guestunmount', mpoint]) 
        print(f"\tSet hostname to be {vm_name}")

    except Exception as e:
        print(e)
        sys.exit(1)

def is_host_in_network_by_name(conn, network_name, host_name, expected_ip):
    """
    Check if a host with the given name is already in the network with the expected IP address.
    
    :param conn: libvirt connection object
    :param network_name: Name of the network
    :param host_name: Name of the host to check
    :param expected_ip: Expected IP address of the host
    :return: True if the host is in the network with the expected IP, False otherwise
    """
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
                        print(f"WARN: {host_name} exists but last octet of IP {expected_ip} != {last_octet} from {host.get('ip')}")
                        return False
                    else:
                        return True
        return False

    except libvirt.libvirtError as e:
        print(f"Error: {e}")
        return False

def remove_ssh_host_keys(hostname):
    def actual_remove(hostname, path):
        print(f"\tRemoving ssh key for {hostname} from {path}")
        subprocess_tabinated(["ssh-keygen", "-f", path, "-R", hostname])

    # Check if the script is running as root
    is_root = os.getuid() == 0

    # If running as root, check if it's a sudo session
    sudo_user = os.environ.get('SUDO_USER')

    # Determine the known_hosts file path for the current user (root or non-root)
    current_user_known_hosts = os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")

    # Remove the host key for the current user (root or non-root)
    actual_remove(hostname, current_user_known_hosts)

    # If running as root in a sudo session, also remove the host key for the original user
    if is_root and sudo_user:
        original_user_known_hosts = os.path.join(os.path.expanduser(f"~{sudo_user}"), ".ssh", "known_hosts")
        actual_remove(hostname, original_user_known_hosts)

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
        print(f"Error executing command in VM: {e}", file=sys.stderr)
        return None

def create_node(conn, src_vm, target_vm, network_name=None, network=None, target_ip=None, hds=None, use_existing=False):
    print(f"CREATING {target_vm} by cloning {src_vm} with target ip of {target_ip} and hds {hds}")
    if not check_vm_status(conn, src_vm, shutdown=True, destroy=False):
        print(f"\tWarning: VM {src_vm} is not appropriately shutdown.")
        sys.exit(1)
    if use_existing and check_vm_status(conn, target_vm, shutdown=True, destroy=False):
        print(f"\tReusing existing VM {target_vm}")
        mac_address = None
    else:
        if not check_vm_status(conn, target_vm, shutdown=True, destroy=True):
            print(f"\tWarning: VM {target_vm} could not be cleaned up.")

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
        #print(f"\tManually applying inheritance in the yaml inventory file")
        for group_name, group_info in inventory.items():
            print(f"\tProcessing group: {group_name}")
            group_vars = group_info.get('vars', {}).copy()
            if parent_vars:
                group_vars.update(parent_vars)
            if 'hosts' in group_info:
                for host_name, host_info in group_info['hosts'].items():
                    host_info.update(group_vars)
            if 'children' in group_info:
                apply_group_vars_to_hosts(group_info['children'], group_vars)

    print(f"Parsing inventory file {file}")
    with open(file, 'r') as f:
        inventory = yaml.safe_load(f) 

    # add inheritance here manually since ansible does this for us
    apply_group_vars_to_hosts(inventory)
    return inventory

def Fatal(msg):
    print(f"FATAL ERROR: {msg}")
    sys.exit(-1)

def get_inventory_value(inventory, keys, default=None):
    try:
        value = inventory
        for key in keys.split('.'):
            value = value[key]
        return value
    except KeyError:
        Fatal(f"Missing '{keys}' in the inventory file.")

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
    # Start the cloned VMs
    for hname in hosts:
        print(f"Starting {hname},")
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
    avail = check_vm_status(conn, args.bootstrap_vm, shutdown=False, destroy=False)
    print(f"Bootstrap VM {args.bootstrap_vm} {'is' if avail else 'is not'} available for re-use to create gold images if needed.")
    avail = check_network_exists(conn, args.virt_network)
    print(f"Network '{args.virt_network}' {'is' if avail else 'is not'} available for re-use.")

    lversion = get_inventory_value(inventory, 'all.vars.lustre.version')
    zversion = get_inventory_value(inventory, 'all.vars.zfs.version')
    golds = get_gold_definitions(vm_dir, lversion, zversion)
    for group,gold in golds.items(): 
        pattern = f"{gold['image_prefix']}*.img"
        for f in glob.glob(pattern):
            print(f"{f.split('/')[-1]} is available to create gold VM for {group}")
        avail = check_vm_status(conn, gold['hname'], shutdown=False, destroy=False)
        print(f"Gold VM {gold['hname']} {'is' if avail else 'is not'} available for re-use to create {group} if needed.")

    for host in hosts:
        avail = check_vm_status(conn, host, shutdown=False, destroy=False)
        print(f"Host VM {host} {'is' if avail else 'is not'} available for re-use to create cluster if needed.")


# helper function to make sure we rebuild only what is necessary
def build_needed(conn, resource, user_overrides, Type):
    if user_overrides and Type in user_overrides:
        print(f"Need to build {resource} because of user specification")
        return True

    if Type in ['bootstrap', 'vms', 'golds']:
        avail = check_vm_status(conn, resource, shutdown=False, destroy=False)
        if not avail:
            print(f"Need to build initial resource {resource}")
            return True
    elif Type == 'network':
        avail = check_network_exists(conn, resource)
        if not avail:
            print(f"Need to build initial resource {resource}")
            return True
    else:
        Fatal(f"Illegal resource type {Type}")

    print(f"Resource {resource} does not require a rebuild")
    return False
        
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='''Create libvirt VMs, install, configure, mount, test a Lustre cluster. Defaults to reuse resources and run all playbooks.
                       Use --rebuilt and --skip to override.''',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter  # Add this line
    )
    parser.add_argument('-b', '--bootstrap_vm',      default='bootstrap',                       help='Name of the base VM.')
    parser.add_argument('-i', '--install_playbook',  default='./ansible/install_all.yaml',      help='Name of the ansible install playbook')
    parser.add_argument('-c', '--config_playbook',   default='./ansible/configure_lustre.yaml', help='Name of the ansible configure playbook')
    parser.add_argument('-t', '--test_playbook',     default='./ansible/test_lustre.yaml',      help='Name of the ansible test playbook')
    parser.add_argument('-v', '--ansible_verbosity', default=0, type=int,                       help='Ansible verbosity')
    parser.add_argument('-n', '--virt_network',      default='hostonly-net',                    help='Name of virtual network to use/create')
    parser.add_argument('--rebuild', action='append', choices=['bootstrap', 'network', 'golds', 'vms', 'all'],    
                                                                                                help='Rebuild specified items (instead of re-using) if they exist')
    parser.add_argument('--skip',    action='append',   choices=['config', 'test'],             help='Skip specified steps (can be used multiple times)')
    parser.add_argument('--show',    action='store_true',                                       help='Show available resources which can be re-used and then quit')
    parser.add_argument('inventory_file',                         type=str,                     help='Path to the ansible inventory file')
    args = parser.parse_args()

    die_unless_root()

    # open the ansible inventory file and pull key items
    inventory = load_yaml(args.inventory_file)
    hosts   = extract_host_details(inventory, ['clients', 'servers'])
    network = get_inventory_value(inventory, 'all.vars.network')
    vm_dir  = get_inventory_value(inventory, 'all.vars.vm_dir')
    network['name'] = args.virt_network # define it here because we use it elsewhere

    # check that the images directory exists 
    check_images_directory(vm_dir)

    # check for the install playbook
    if not os.path.exists(args.install_playbook):
        Fatal(f"Ansible install playbook {args.install_playbook} does not exist")

    # Connect to libvirt
    with LibvirtConnection() as conn:

        if args.show:
            show_resources(conn, args, inventory, vm_dir, hosts)
            sys.exit(0)

        # create the initial bootstrap VM if needed 
        if build_needed(conn, args.bootstrap_vm, args.rebuild, 'bootstrap'):
            install_initial_vm(conn, args.bootstrap_vm, inventory, args.ansible_verbosity)

        # ensure the bootstrap VM is ready 
        if not check_vm_status(conn, args.bootstrap_vm):
            Fatal(f"VM {args.bootstrap_vm} does not exist or is not shut off.")

        if build_needed(conn, args.virt_network, args.rebuild, 'network'):
            remove_network_if_exists(conn, args.virt_network)

        # make or fetch the gold image for the servers and clients
        rebuilds = {}
        for resource in [ 'vms', 'golds' ]:
            if args.rebuild and resource in args.rebuild:
                rebuilds[resource] = True
            else:
                rebuilds[resource] = False 
        pprint(rebuilds)
        gold_vms = {}
        (gold_vms['servers'], gold_vms['clients']) = make_gold_vms(
            conn = conn, 
            bootstrap_vm = args.bootstrap_vm, 
            images = vm_dir, 
            inventory = inventory, 
            inventory_file = args.inventory_file, 
            playbook_file = args.install_playbook, 
            rebuild_vms = rebuilds['vms'],
            rebuild_golds = rebuilds['golds'],
            verbosity = args.ansible_verbosity)

        # now clone the base image for each requested lustre node
        if args.rebuild and 'vms' in args.rebuild:
            use_existing = False
        else:
            use_existing = True
        for hname,hinfo in hosts.items():
            hip = hinfo['ip']
            hds = hinfo['hds']
            gvm = gold_vms[hinfo['group']]
            create_node(conn, gvm, hname, network['name'], network['addr'], hip, hds, use_existing)
            print(f"\tCreated {hname}:{network['addr']}.{hip} from {gvm}.")

        # Restart libvirt services to apply changes
        conn.restart()

        # reboot the freshly coned VMs to make sure changes are applied appropriately
        restart_hosts(conn, hosts)

        # configure the lustre system
        if args.skip is not None and 'config' in args.skip:
            print(f"Skipping config as requested")
        else:
            run_playbook(None, args.inventory_file, args.config_playbook, None, args.ansible_verbosity)

        # test the lustre system
        if args.skip is not None and 'config' in args.skip:
            print(f"Skipping testing as requested")
        else:
            run_playbook(None, args.inventory_file, args.test_playbook, None, args.ansible_verbosity)

    print(f"Setup completed. Lustre cluster should now be running with new NICs attached to {network['name']}.")

if __name__ == "__main__":
    main()


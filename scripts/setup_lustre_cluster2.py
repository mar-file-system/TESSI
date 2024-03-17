#! /usr/bin/env python3.8

import ansible_runner
import argparse
import inspect
import libvirt
import os
import paramiko
import pwd
import socket
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import yaml

from uuid import uuid4

def wait_for_ssh(host, port=22, username='root', timeout=300, interval=3):
    """
    Wait for an SSH connection to become available.

    Args:
        host (str): The hostname or IP address of the target node.
        port (int): The SSH port.
        username (str): The username for the SSH connection.
        timeout (int): The maximum time to wait in seconds.
        interval (int): The interval between connection attempts in seconds.

    Returns:
        bool: True if the SSH connection is available, False if the timeout is reached.
    """
    print(f"\tWaiting for {host} to be reachable")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with paramiko.SSHClient() as client:
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(host, port=port, username=username, timeout=timeout)
                # SSH connection is successful
                return True
        except (socket.gaierror, paramiko.ssh_exception.NoValidConnectionsError, paramiko.ssh_exception.SSHException):
            # Connection failed, wait and try again
            print(f"\tWaiting again for {host} to be reachable")
            time.sleep(interval)

    # Timeout reached, connection failed
    return False

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


def restart_libvirt(conn):
    time.sleep(5)
    conn.close()
    print("Restarting libvirt network")
    subprocess.run(["systemctl", "restart", "virtlogd.socket"])
    subprocess.run(["systemctl", "restart", "libvirtd"])
    time.sleep(5)
    conn = libvirt_connect()
    return conn

def check_images_directory(images):
    if not os.path.isdir(images):
        Fatal(f"Specified image directory {images} is not a valid directory.")
    os.makedirs(images + '/lustre/servers', exist_ok=True)
    os.makedirs(images + '/lustre/clients', exist_ok=True)

# this recreates the libvirt connection so it has to return it
def create_gold(conn, base_vm, hname, inventory_file, playbook_file, group, verbosity):

    if not check_vm_status(conn, base_vm):
        Fatal(f"VM {base_vm} does not exist or is not shut off.")

    if group not in [ 'clients', 'servers' ]:
        Fatal(f"Unknown group {group}")

    # clone the gold server and start it
    print(f"\tCloning {hname} from {base_vm}") 
    create_node(conn, base_vm, hname) 
    conn = restart_libvirt(conn)
    print(f"\tStarting {hname}") 
    dom = conn.lookupByName(hname)
    dom.create()
    if not wait_for_ssh(hname):
        Fatal("Timed out waiting for node to become ready")

    # might need to reboot it here to affect the selinux and firewall config
    # might not be necessary however

    run_playbook(hname, inventory_file, playbook_file, group, verbosity)

    # shut it down
    dom.destroy()
    return conn

def run_playbook(hname, inventory_file, playbook_file, group, verbosity):
    hosts = [hname]
    temp_inventory = create_temp_inventory_file(hosts, group=group)

    # get absolute paths
    playbook_file = os.path.abspath(playbook_file)
    inventory_file = os.path.abspath(inventory_file)

    os.environ['ANSIBLE_HOST_KEY_CHECKING'] = 'False'

    # now run the ansible playbook 
    result = ansible_runner.run(
        playbook=playbook_file,
        inventory=[inventory_file, temp_inventory],
        verbosity=verbosity,
        limit=hname
    )

    if result.status == 'successful':
        print("Playbook executed successfully.")
    else:
        Fatal(f"Playbook execution failed with status: {result.status}")

def make_gold_vms(conn,base_vm,images,inventory,inventory_file,playbook_file,verbosity):
    lversion = get_inventory_value(inventory, 'all.vars.lustre.version')
    zversion = get_inventory_value(inventory, 'all.vars.zfs.version')
    print(f"Need gold server {lversion}.{zversion}")
    srv_image = f"{images}/lustre/servers/{lversion}.{zversion}.img"
    srv_hname = 'gold-lustre-server'

    cli_image = f"{images}/lustre/clients/{lversion}.img"
    cli_hname = 'gold-lustre-client'

    if os.path.exists(cli_image):
        Fatal(f"Image {cli_image} available. TODO: next steps here")
        pass
    else:
        conn = create_gold(conn, base_vm, cli_hname, inventory_file, playbook_file, 'clients', verbosity)
        stash_vm(conn, cli_image, cli_hname)

    if os.path.exists(srv_image):
        Fatal(f"Image {srv_image} available. TODO: next steps here")
        pass
    else:
        conn = create_gold(conn, base_vm, srv_hname, inventory_file, playbook_file, 'servers', verbosity)
        stash_vm(conn, srv_image, srv_hname)

    return (srv_hname, cli_hname) 

def check_vm_status(conn,vm_name,shutdown=True,destroy=False):
    """Check if the VM exists and is shut off."""
    try:
        dom = conn.lookupByName(vm_name)
    except libvirt.libvirtError:
        print(f"\tVM {vm_name} does not exist.")
        return False

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
        print(f"\tSuccessfully cleaned up {vm_name}.")

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
    """Check if the specified network exists."""
    try:
        conn.networkLookupByName(network_name)
        return True
    except libvirt.libvirtError:
        return False

def setup_hostonly_network(conn, network, network_name, mac_addresses = ''):
    """Set up host-only network with optional static MAC address assignments."""
    network_xml = f"""
<network>
  <name>{network_name}</name>
  <bridge name='virbr1' stp='on' delay='0'/>
  <ip address='{network}.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='{network}.2' end='{network}.254'/>
      {mac_addresses}
    </dhcp>
  </ip>
</network>
"""
    if check_network_exists(conn,network_name):
        print(f"\tNetwork '{network_name}' exists. Cleaning it up.")
        network = conn.networkLookupByName(network_name)
        network.destroy()
        # the bash version had a sleep 2 here. Is it not needed?
        network.undefine()
    network = conn.networkDefineXML(network_xml)
    network.setAutostart(True)
    network.create()

# run subprocess but put tabs in front of its output
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
    #print("DEBUG" + repr(output)) # show the special characters so we can figure out why there are double newlines in this output


def clone_vm(base_vm, new_vm):
    """Clone a VM."""
    clone_command = f"virt-clone --original {base_vm} --name {new_vm} --auto-clone --nonsparse"
    subprocess_tabinated(clone_command.split())

def add_nic_to_vm(conn, vm_name, network_name, mac_address=None):
    """Add a NIC to a VM."""
    if not mac_address:
        mac_address = "02:%s" % ":".join(["%02x" % (i,) for i in os.urandom(5)])
    dom = conn.lookupByName(vm_name)
    xml_desc = dom.XMLDesc()
    root = ET.fromstring(xml_desc)
    devices = root.find('devices')
    interface = ET.SubElement(devices, 'interface', type='network')
    ET.SubElement(interface, 'mac', address=mac_address)
    ET.SubElement(interface, 'source', network=network_name)
    ET.SubElement(interface, 'model', type='virtio')
    conn.defineXML(ET.tostring(root).decode())
    return mac_address

def libvirt_connect():
    conn = libvirt.open('qemu:///system')
    if conn is None:
        print("Failed to open connection to qemu:///system")
        sys.exit(1)
    return conn

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

def set_hostname_selinux_lustre_options(conn, vm_name, selinux, lopts):
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

        # update the lustre options
        if lopts:
            lfile = os.path.join(mpoint, 'etc/modprobe.d/lustre.conf')
            with open(lfile, 'w+') as file:
                file.write(lopts + '\n')

        # disable the firewall
        firewalld_service = os.path.join(mpoint, 'etc/systemd/system/firewalld.service')
        if os.path.lexists(firewalld_service):
            os.remove(firewalld_service)
        os.symlink('/dev/null', firewalld_service)

        # unmount the disk image
        subprocess_tabinated(['guestunmount', mpoint]) 
        print(f"\tSet hostname to be {vm_name}")

    except Exception as e:
        print(e)
        sys.exit(1)

def create_node(conn, src_vm, target_vm, network_name=None, network=None, target_ip=None, mac_addr_map=None, hds=None, lopts=None):
    print(f"CREATING {target_vm} by cloning {src_vm} with target ip of {target_ip} and hds {hds}")
    if not check_vm_status(conn, src_vm, shutdown=True, destroy=False):
        print(f"\tWarning: VM {src_vm} is not appropriately shutdown.")
        sys.exit(1)
    if not check_vm_status(conn, target_vm, shutdown=True, destroy=True):
        print(f"\tWarning: VM {target_vm} could not be cleaned up.")

    # Clone the base VM
    clone_vm(src_vm, target_vm)

    # Add NIC to the cloned VM
    if target_ip:
        mac_address = add_nic_to_vm(conn, target_vm, network_name)
        mac_addr_map[target_vm] = [ mac_address, target_ip ]

        # give static IP assignment of the new VM to the network
        mac_addresses = '\n'.join(f'      <host mac="{mac}" name="{name}" ip="{network}.{ip}"/>' for name, (mac,ip) in mac_addr_map.items())
        print(mac_addresses)
        setup_hostonly_network(conn, network, network_name, mac_addresses)

    set_hostname_selinux_lustre_options(conn,target_vm, 'disabled', lopts)

    if hds:
        # this get_letter thing is just a way to iterate through the alphabet to create good HDD names
        get_letter = lambda x: chr(ord('b') + x )
        for idx,hd in enumerate(hds):
            path = f"{get_image_storage_pool_path(conn)}/{target_vm}_hdd{idx}_{hd}GB"
            create_disk_image(path, f"{hd}G")
            attach_disk_to_vm(target_vm, path, f"sd{get_letter(idx)}")

def extract_host_details(d, host_details):
    if isinstance(d, dict):
        for key, value in d.items():
            if key == 'hosts':
                for host, attributes in value.items():
                    host_details[host] = attributes
            else:
                extract_host_details(value, host_details)

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

def main():

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='VM and network setup script using libvirt.')
    parser.add_argument('-b', '--base_vm',     default='freshinstall', help='Name of the base VM.')
    parser.add_argument('-p', '--playbook',    default='./ansible/install_all.yaml', help='Name of the ansible install playbook')
    parser.add_argument('-v', '--ansible_verbosity', default=0, type=int, help='Ansible verbosity')
    parser.add_argument('inventory_file',      type=str,               help='Path to the ansible inventory file')
    args = parser.parse_args()

    # Check if script is run as root
    if os.geteuid() != 0:
        print("Must be run as root")
        sys.exit(1)

    # open the ansible inventory file 
    inventory = load_yaml(args.inventory_file)

    # Connect to libvirt
    conn = libvirt_connect()

    # pull key things from the ansible inventory file
    hosts = {}
    extract_host_details(inventory, hosts)
    network = get_inventory_value(inventory, 'all.vars.network')
    lopts = get_inventory_value(inventory, 'all.vars.lustre.modprobe_opts')
    images = get_inventory_value(inventory, 'all.vars.git.images')
    network['name'] = 'hostonly-net' # define it here because we use it elsewhere

    # check that the images directory exists and is part of a git repo
    check_images_directory(images)

    # check for the playbook
    if not os.path.exists(args.playbook):
        Fatal(f"Ansible install playbook {args.playbook} does not exist")

    # make or fetch the gold image for the server
    make_gold_vms(conn, args.base_vm, images, inventory, args.inventory_file, args.playbook, args.ansible_verbosity) 

    sys.exit(0)

    # Main execution starts here
    setup_hostonly_network(conn, network['addr'], network['name'])

    if not check_vm_status(conn, args.base_vm):
        print(f"Warning: VM {args.base_vm} does not exist or is not shut off.")
        sys.exit(1)

    # create the base image
    mac_addr_map = {}
    create_node(conn, args.base_vm, args.lustre_gold, network['name'], network['addr'], args.ip_addr, mac_addr_map, None, lopts)

    # now close the base image for each requested lustre node
    for hname,hinfo in hosts.items():
        hip = hinfo['ip']
        hds = hinfo['hds']
        create_node(conn, args.lustre_gold, hname, network['name'], network['addr'], hip, mac_addr_map, hds, lopts)
        print(f"\tCreated {hname}:{network['addr']}.{hip}.")

    # Restart libvirt services to apply changes
    conn = restart_libvirt(conn)

    # Start the cloned VMs
    dom = conn.lookupByName(args.lustre_gold)
    dom.create()
    for hname in hosts:
        print(f"Starting {hname},")
        dom = conn.lookupByName(hname)
        dom.create()
    time.sleep(10)

    # reboot them
    for hname in hosts:
        print(f"Reboot {hname} to try to ensure it gets its IP addresses correctly reported to libvirt")
        dom = conn.lookupByName(hname)
        dom.reboot()
    time.sleep(10)

    # Close the libvirt connection
    conn.close()

    print(f"Setup completed. Lustre cluster should now be running with new NICs attached to {network['name']}.")

if __name__ == "__main__":
    main()


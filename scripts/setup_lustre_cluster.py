#! /usr/bin/env python3.6

import argparse
import inspect
import libvirt
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import yaml

from uuid import uuid4

def check_vm_status(conn,vm_name,shutdown=True,destroy=False):
    """Check if the VM exists and is shut off."""
    try:
        dom = conn.lookupByName(vm_name)
    except libvirt.libvirtError:
        print(f"VM {vm_name} does not exist.")
        return False

    # does the caller require it to be shutdown?
    if shutdown:
        # Check if the VM is running and stop it if so
        if dom.isActive():
            dom.destroy()  # This forcibly stops the domain
            print(f"VM {vm_name} was running. Stopped it.")

    # does the caller require it to be destroyed?
    if destroy:
        delete_vm_storage(conn, vm_name)
        # Undefine the VM, removing all associated storage and snapshots
        dom.undefineFlags(
            libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE |
            libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA |
            libvirt.VIR_DOMAIN_UNDEFINE_NVRAM |
            0)
        print(f"Successfully cleaned up {vm_name}.")

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
                        print(f"Deleted volume: {disk_path}")
                    except libvirt.libvirtError as e:
                        print(f"Error deleting volume {disk_path}: {e}")

    except libvirt.libvirtError as e:
        print(f"Failed to find or access VM {vm_name} for storage deletion: {e}")

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
        print(f"Network '{network_name}' exists. Cleaning it up.")
        network = conn.networkLookupByName(network_name)
        network.destroy()
        # the bash version had a sleep 2 here. Is it not needed?
        network.undefine()
    network = conn.networkDefineXML(network_xml)
    network.setAutostart(True)
    network.create()

def clone_vm(base_vm, new_vm):
    """Clone a VM."""
    clone_command = f"virt-clone --original {base_vm} --name {new_vm} --auto-clone --nonsparse"
    subprocess.run(clone_command.split())

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
        subprocess.run(command, check=True)
        print(f"Disk image {image_path} created with size {size}.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to create disk image: {e}")
        sys.exit(1)

def attach_disk_to_vm(vm_name, disk_path, target_dev, cache_mode='none', persistent=True):
    """Attach a disk to a VM using virsh."""
    command = ["virsh", "attach-disk", vm_name, disk_path, target_dev, "--cache", cache_mode]
    if persistent:
        command.append("--persistent")
    try:
        subprocess.run(command, check=True)
        print(f"Disk {disk_path} attached to {vm_name} as {target_dev}.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to attach disk to VM: {e}")
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

def set_hostname_selinux_lustre_options(conn, vm_name, selinux='disabled', lopts=None):
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

        subprocess.run(['guestmount', '-a', vmimage, '-i', mpoint], check=True)
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
            if not os.path.exists(lfile):
                raise Exception(f"Warning: {lfile} not found")
            with open(lfile, 'w') as file:
                file.write(lopts)

        # unmount the disk image
        subprocess.run(['guestunmount', mpoint], check=True)
        print(f"Set hostname to be {vm_name}")

    except Exception as e:
        print(e)
        sys.exit(1)

def create_node(conn, src_vm, target_vm, network_name, network, target_ip, mac_addr_map, hds=None, lopts=None):
    if not check_vm_status(conn, src_vm, shutdown=True, destroy=False):
        print(f"Warning: VM {src_vm} is not appropriately shutdown.")
        sys.exit(1)
    if not check_vm_status(conn, target_vm, shutdown=True, destroy=True):
        print(f"Warning: VM {target_vm} could not be cleaned up.")

    # Clone the base VM
    clone_vm(src_vm, target_vm)

    # Add NIC to the cloned VM
    mac_address = add_nic_to_vm(conn, target_vm, network_name)
    mac_addr_map[target_vm] = [ mac_address, target_ip ]

    # give static IP assignment of the new VM to the network
    mac_addresses = '\n'.join(f'      <host mac="{mac}" name="{name}" ip="{network}.{ip}"/>' for name, (mac,ip) in mac_addr_map.items())
    print(mac_addresses)
    setup_hostonly_network(conn, network, network_name, mac_addresses)

    set_hostname_selinux_lustre_options(conn,target_vm, lopts)

    # this get_letter thing is just a way to iterate through the alphabet to create good HDD names
    get_letter = lambda x: chr(ord('b') + x )
    try:
        for idx,hd in enumerate(hds):
            path = f"{get_image_storage_pool_path(conn)}/{target_vm}_hdd{idx}_{hd}GB"
            create_disk_image(path, f"{hd}G")
            attach_disk_to_vm(target_vm, path, f"sd{get_letter(idx)}")
    except TypeError:
        pass # hds can be none 

def restart_networking():
    print("Restarting libvirt network")
    subprocess.run(['systemctl', 'restart', 'virtlogd.socket'], check=True)
    subprocess.run(['systemctl', 'restart', 'libvirtd'], check=True)

def main():

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='VM and network setup script using libvirt.')
    parser.add_argument('-v', '--base_vm',     default='freshinstall', help='Name of the base VM.')
    parser.add_argument('-l', '--lustre_gold', default='lustrebase',   help='Name for the Lustre base VM clone.')
    parser.add_argument('-a', '--ip_addr',     default='101',          help='IP address to assign to the Lustre base VM.')
    parser.add_argument('config_file',         type=str,               help='Path to the configuration file')
    args = parser.parse_args()

    # Check if script is run as root
    if os.geteuid() != 0:
        print("Must be run as root")
        sys.exit(1)

    # open the config file
    with open(args.config_file, 'r') as file:
        config = yaml.safe_load(file) 

    # Connect to libvirt
    conn = libvirt_connect()

    # pull key things from config file
    network = config['system']['network']
    hosts   = config['system']['hosts']
    lopts   = config['system']['lustre_options']
    print(f"Lustre options are {lopts}")

    # Main execution starts here
    setup_hostonly_network(conn, network['addr'], network['name'])

    if not check_vm_status(conn, args.base_vm):
        print(f"Warning: VM {args.base_vm} does not exist or is not shut off.")
        sys.exit(1)

    mac_addr_map = {}
    create_node(conn, args.base_vm, args.lustre_gold, network['name'], network['addr'], args.ip_addr, mac_addr_map, None, lopts)

    for hname,hinfo in hosts.items():
        hip = hinfo['ip']
        hds = hinfo['hds']
        create_node(conn, args.lustre_gold, hname, network['name'], network['addr'], hip, mac_addr_map, hds, lopts)
        print(f"Created {hname}:{network['addr']}.{hip}.")

    # Restart libvirt services to apply changes
    time.sleep(2)
    conn.close()
    subprocess.run(["systemctl", "restart", "virtlogd.socket"])
    subprocess.run(["systemctl", "restart", "libvirtd"])
    time.sleep(2)
    conn = libvirt_connect()

    # Start the cloned VMs
    dom = conn.lookupByName(args.lustre_gold)
    dom.create()
    for hname in hosts:
        print(f"Starting {hname}")
        dom = conn.lookupByName(hname)
        dom.create()

    # Close the libvirt connection
    conn.close()

    # restart the network to help everyone get their IP addresses
    restart_networking()

    print(f"Setup completed. Lustre cluster should now be running with new NICs attached to {network['name']}.")

if __name__ == "__main__":
    main()


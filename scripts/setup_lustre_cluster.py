#! /usr/bin/env python3.6

import argparse
import os
import sys
import libvirt
import time
import xml.etree.ElementTree as ET
from uuid import uuid4
import subprocess

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

def setup_hostonly_network(conn, network, network_name, mac_addresses):
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

def create_node(conn, src_vm, target_vm, network_name, network, target_ip, mac_addr_map):
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


def main():

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='VM and network setup script using libvirt.')
    parser.add_argument('-v', '--base_vm', default='freshinstall', help='Name of the base VM.')
    parser.add_argument('-l', '--base_lustre', default='lustrebase', help='Name for the Lustre base VM clone.')
    parser.add_argument('-n', '--network_name', default='hostonly-net', help='Name of the virtual network.')
    parser.add_argument('-a', '--ip_addr', default='101', help='IP address to assign to the Lustre base VM.')
    parser.add_argument('-i', '--network', default='192.168.56', help='Hostonly network.')
    args = parser.parse_args()

    # Check if script is run as root
    if os.geteuid() != 0:
        print("Must be run as root")
        sys.exit(1)

    # Connect to libvirt
    conn = libvirt_connect()

    # Main execution starts here
    setup_hostonly_network(conn, args.network, args.network_name, "")

    if not check_vm_status(conn, args.base_vm):
        print(f"Warning: VM {args.base_vm} does not exist or is not shut off.")
        sys.exit(1)

    mac_addr_map = {}
    create_node(conn, args.base_vm, args.base_lustre, args.network_name, args.network, args.ip_addr, mac_addr_map)

    # now create each desired lustre node
    hosts = {
        'mds00':  '10',
        'mds01':  '20',
        'oss00':  '30',
        'oss01':  '40',
        'client': '50'
    }
    for hname,hip in hosts.items():
        create_node(conn, args.base_vm, hname, args.network_name, args.network, hip, mac_addr_map)
        print(f"Created {hname}:{args.network}.{hip}. TODO: Need to create from {args.base_lustre} and need to set up disks")

    # Restart libvirt services to apply changes
    time.sleep(2)
    conn.close()
    subprocess.run(["systemctl", "restart", "virtlogd.socket"])
    subprocess.run(["systemctl", "restart", "libvirtd"])
    time.sleep(2)
    conn = libvirt_connect()

    # Start the cloned VMs
    dom = conn.lookupByName(args.base_lustre)
    dom.create()
    for hname in hosts:
        print(f"Starting {hname}")
        dom = conn.lookupByName(hname)
        dom.create()

    # Close the libvirt connection
    conn.close()

    print(f"Setup completed. Lustre cluster should now be running with new NICs attached to {args.network_name}.")

if __name__ == "__main__":
    main()


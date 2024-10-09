#! /usr/bin/env python3.8

import argparse
import datetime
import libvirt
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

import run_tassi

# global connection variable
conn = None

def delete_domain(domain,conn):
    run_tassi.check_vm_status(conn,domain.name(),shutdown=True,destroy=True)

def state_to_string(state):
    state_strings = {
        libvirt.VIR_DOMAIN_NOSTATE: 'No State',
        libvirt.VIR_DOMAIN_RUNNING: 'Running',
        libvirt.VIR_DOMAIN_BLOCKED: 'Blocked on resource',
        libvirt.VIR_DOMAIN_PAUSED: 'Paused by user',
        libvirt.VIR_DOMAIN_SHUTDOWN: 'Being shut down',
        libvirt.VIR_DOMAIN_SHUTOFF: 'Shut off',
        libvirt.VIR_DOMAIN_CRASHED: 'Crashed',
        libvirt.VIR_DOMAIN_PMSUSPENDED: 'Suspended by guest power management',
    }

    return state_strings.get(state, "Unknown")

import libvirt
import os
import xml.etree.ElementTree as ET

def print_disks(domain):
    # Get the domain's XML description
    xml_desc = domain.XMLDesc()
    root = ET.fromstring(xml_desc)

    global conn

    for disk in root.findall('.//devices/disk'):
        if disk.get('device') == 'disk':
            target = disk.find('target')
            if target is not None:
                target_dev = target.get('dev')
            else:
                target_dev = "Unknown"

            source = disk.find('source')

            # Handle volume-based disks
            if source is not None and 'volume' in source.attrib:
                pool_name = source.get('pool')
                volume_name = source.get('volume')

                if pool_name and volume_name:
                    # Look up the storage pool and volume
                    pool = conn.storagePoolLookupByName(pool_name)
                    vol = pool.storageVolLookupByName(volume_name)
                    
                    # Get the volume info
                    vol_info = vol.info()
                    size_bytes = vol_info[1]  # Second element is the size in bytes
                    
                    print(f"\tHDD Size: {size_bytes / (1024 ** 3):.2f} GB - Dev: {target_dev}")
                else:
                    print(f"\tHDD Size: Volume info not found for {target_dev}")

            # Handle file-based disks
            elif source is not None and 'file' in source.attrib:
                disk_file = source.get('file')
                if disk_file and os.path.exists(disk_file):
                    # Get the size of the disk file
                    size_bytes = os.path.getsize(disk_file)
                    print(f"\tHDD Size: {size_bytes / (1024 ** 3):.2f} GB - Dev: {target_dev}")
                else:
                    print(f"\tHDD Size: Disk source file not found or inaccessible for {target_dev}")

            else:
                print(f"\tHDD Size: No valid disk source for {target_dev}")


def print_networks(domain):
    addresses = domain.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE)

    xml_desc = domain.XMLDesc()
    dom = minidom.parseString(xml_desc)
    interfaces = dom.getElementsByTagName('interface')
    for interface in interfaces:
        mac_element = interface.getElementsByTagName('mac')[0]
        mac_address = mac_element.getAttribute('address')
        print(f"\tMAC Address: {mac_address}")

    # Extract and print the IP address
    for (name, val) in addresses.items():
        for addr in val['addrs']:
            if addr['type'] == libvirt.VIR_IP_ADDR_TYPE_IPV4:
                print(f"\tIP Address: {addr['addr']}")

def print_kernel(domain):
    (ret, kernel) = get_kernel(domain.name())
    if ret == 0:
        print(f"\tKernel Version: {kernel}")
    else:
        print(f"\tKernel Version: Error executing command in VM - {kernel}")

def print_distro(domain):
    (ret, distro) = get_distro(domain.name())
    if ret == 0:
        print(f"\tDistribution: {distro}")
    else:
        print(f"\tKernel Version: Error executing command in VM - {distro}")

# returns 0, kernel on success
# returns 1, error string on failure
def get_kernel(hname):
    command = f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {hname} uname -r"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if result.returncode == 0:
        return(0, result.stdout.strip())
    else:
        return(1, result.stderr.strip())

# returns 0, distro on success
# returns 1, error string on failure
def get_distro(hname):
    command = f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {hname} grep PRETTY_NAME /etc/os-release "
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if result.returncode == 0:
        return(0, result.stdout.strip().split('=')[1])
    else:
        return(1, result.stderr.strip())

def print_snapshots(domain):
    snapshots = domain.listAllSnapshots()
    list_snaps = {}
    if snapshots:
        print("\tSnapshots:")
        for snapshot in snapshots:
            s_name = snapshot.getName()
            s_xml = snapshot.getXMLDesc()
            xroot = ET.fromstring(s_xml)
            s_desc = xroot.find('.//description').text if xroot.find('.//description') is not None else "No Description"
            s_time = xroot.find('.//creationTime').text if xroot.find('.//creationTime') is not None else "No Timestamp"
            s_strtime = datetime.datetime.fromtimestamp(int(s_time)).strftime('%Y-%m-%d %H:%M:%S')
            list_snaps[s_time] = f"\t- {s_name} {s_desc} {s_strtime}"
    [print(value) for key, value in sorted(list_snaps.items(), reverse=True)]

def main():
    parser = argparse.ArgumentParser(description='Display, and potentially delete, virtual machines.')
    parser.add_argument('--delete', action='store_true', help='Prompt for each VM deletion')
    parser.add_argument('--force-delete', action='store_true', help='Delete all VMs without prompting')
    args = parser.parse_args()

    functions = [
        {'ptr': print_kernel,    'name': 'kernel',    'require_running': True},
        {'ptr': print_distro,    'name': 'distro',    'require_running': True},
        {'ptr': print_networks,  'name': 'networks',  'require_running': True},
        {'ptr': print_snapshots, 'name': 'snapshots', 'require_running': True},
        {'ptr': print_disks,     'name': 'disks',     'require_running': False}
    ]

    global conn
    conn = libvirt.open('qemu:///system')
    domains = conn.listAllDomains()
    for domain in sorted(domains, key=lambda domain: domain.name()):
        state = domain.state()[0]  # Get the state integer
        print(f"Name: {domain.name()} - ID: {domain.ID()}, State: {state_to_string(state)}")

        for func_dict in functions:
            if not func_dict['require_running'] or domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING:
                try:
                    func_dict['ptr'](domain)
                except libvirt.libvirtError as e:
                    print(f"ERROR: Error getting {func_dict['name']} for {domain.name()}: {e}")

        if (args.force_delete and 'bootstrap' not in domain.name()) or (args.delete and input(f"PROMPT: Delete {domain.name()}? y/n: ").strip().lower() == 'y'):
            delete_domain(domain,conn)

    conn.close()

if __name__ == '__main__':
    main()


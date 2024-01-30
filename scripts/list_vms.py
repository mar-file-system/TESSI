#! /usr/bin/env python3.6

import datetime
import libvirt
import os
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Connect to the hypervisor
conn = libvirt.open('qemu:///system')

#


# Check if the current user is root
if os.geteuid() != 0:
    sys.exit("Warning: This script must be run as root.")

# Connect to the libvirt daemon
conn = libvirt.open()

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

# List all defined virtual machines
domains = conn.listAllDomains()
for domain in sorted(domains, key=lambda domain: domain.name()):
    state = domain.state()[0]  # Get the state integer
    print(f"Name: {domain.name()}, ID: {domain.ID()}, State: {state_to_string(state)}")

    # Get the domain's XML description
    xml_desc = domain.XMLDesc()
    root = ET.fromstring(xml_desc)

    # if the domain is running, figure out its ip address
    if domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING:
        try:
            # Get the interface addresses for the domain
            addresses = domain.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE)

            # Find all interface elements within the domain XML
            dom = minidom.parseString(xml_desc)
            interfaces = dom.getElementsByTagName('interface')
            for interface in interfaces:
                # Find the MAC address element within each interface
                mac_element = interface.getElementsByTagName('mac')[0]
                mac_address = mac_element.getAttribute('address')
                print(f"\tMAC Address: {mac_address}")

            # Extract and print the IP address
            for (name, val) in addresses.items():
                for addr in val['addrs']:
                    if addr['type'] == libvirt.VIR_IP_ADDR_TYPE_IPV4:
                        print(f"\tIP Address: {addr['addr']}")
        except libvirt.libvirtError as e:
            print(f"Error getting interface addresses for {domain.name()}: {e}")

        try:
            # Get a list of snapshot names for the domain
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

        except libvirt.libvirtError as e:
            print(f"Error getting snapshots for {domain.name()}: {e}")

    # Find all disk elements in the XML
    for disk in root.findall('.//devices/disk'):
        if disk.get('device') == 'disk':
            source = disk.find('source')
            if source is not None:
                disk_file = source.get('file')
                if disk_file and os.path.exists(disk_file):
                    # Get the size of the disk file
                    size_bytes = os.path.getsize(disk_file)
                    print(f"\tHDD Size: {size_bytes / (1024 ** 3):.2f} GB")
                else:
                    print("\tHDD Size: Disk source file not found or inaccessible")

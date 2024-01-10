#! /usr/bin/env python3.6

import datetime
import libvirt
import os
import sys
import xml.etree.ElementTree as ET


# Check if the current user is root
if os.geteuid() != 0:
    sys.exit("Warning: This script must be run as root.")

# Connect to the libvirt daemon
conn = libvirt.open()

# List all defined virtual machines
domains = conn.listAllDomains()
for domain in domains:
    print(f"Name: {domain.name()}, ID: {domain.ID()}, State: {domain.state()}")

    # if the domain is running, figure out its ip address
    if domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING:
        try:
            # Get the interface addresses for the domain
            addresses = domain.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE)

            # Extract and print the IP address
            for (name, val) in addresses.items():
                for addr in val['addrs']:
                    if addr['type'] == libvirt.VIR_IP_ADDR_TYPE_IPV4:
                        print(f"\tIP Address: {addr['addr']}")

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
            print(f"Error getting interface addresses for {domain.name()}: {e}")

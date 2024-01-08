#! /usr/bin/env python3

import libvirt
import os
import sys

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
            if snapshots:
                print("\tSnapshots:")
                for snapshot in snapshots:
                    snapshot_name = snapshot.getName()
                    print(f"\t- {snapshot_name}")

        except libvirt.libvirtError as e:
            print(f"Error getting interface addresses for {domain.name()}: {e}")

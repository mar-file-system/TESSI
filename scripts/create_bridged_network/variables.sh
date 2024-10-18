#!/bin/bash

# Names for the bridges
PHYSICAL_BRIDGE="tassibr0"
VIRTUAL_BRIDGE="tassivirbr0"

# DNSMasq settings
DNSMASQ_CONF="/etc/dnsmasq.conf"
DHCP_RANGE_START="192.168.100.100"
DHCP_RANGE_END="192.168.100.200"
DHCP_SUBNET_MASK="255.255.255.0"
DHCP_LEASE_TIME="12h"

# libvirt network name
LIBVIRT_NET_NAME="tassi_vm_network"

# Other configuration variables can be added here as needed


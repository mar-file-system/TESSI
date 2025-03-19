#!/bin/bash

set -e
set -x

BRIDGE=bbeegfs743
VXLAN_IFNAME=vbeegfs743
VXLAN_CONNAME="br0-${VXLAN_IFNAME}"
LIBVIRT=lbeegfs743 
VXID=4660973
MCAST="239.1.66.82"
LOCAL=$(ip route get 1.1.1.1 | awk '{print $7; exit}')

clean() {
    nmcli connection delete ${VXLAN_CONNAME} || true
    nmcli connection delete ${BRIDGE} || true
    ip link delete ${VXLAN_IFNAME} || true
    ip link delete ${BRIDGE} || true
    echo "Cleaned up ${BRIDGE} and ${VXLAN_IFNAME} (${VXLAN_CONNAME})"
}

if [[ "$1" == "--clean" ]]; then
    clean
    exit 0
fi

# Add and bring up the bridge
nmcli connection add type bridge con-name ${BRIDGE} ifname ${BRIDGE} ipv4.method disabled ipv6.method disabled
nmcli connection up ${BRIDGE}

# Add the VXLAN interface and bring it up explicitly
nmcli connection add type vxlan slave-type bridge con-name ${VXLAN_CONNAME} ifname ${VXLAN_IFNAME} id ${VXID} local ${LOCAL} remote ${MCAST} master ${BRIDGE}
nmcli connection up ${VXLAN_CONNAME}

# Wait a moment to allow the interface to be fully initialized
sleep 2

# Verify that the VXLAN interface now exists
ip link show ${VXLAN_IFNAME} || echo "VXLAN interface ${VXLAN_IFNAME} not found"

# Display the forwarding database (FDB) table
bridge fdb show dev ${VXLAN_IFNAME}


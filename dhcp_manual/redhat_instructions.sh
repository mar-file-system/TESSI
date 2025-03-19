#!/bin/bash

set -e
set -x

BRIDGE=bbeegfs743
VXLAN_IFNAME=vbeegfs743
VXID=4660973
MCAST="239.1.66.82"
LOCAL=$(ip route get 1.1.1.1 | awk '{print $7; exit}')
PHYSICAL_IFACE=eno1 # Replace with your physical interface

clean() {
    nmcli connection delete ${BRIDGE} || true
    ip link delete ${VXLAN_IFNAME} || true
    ip link delete ${BRIDGE} || true
    echo "Cleaned up ${BRIDGE} and ${VXLAN_IFNAME}"
}

if [[ "$1" == "--clean" ]]; then
    clean
    exit 0
fi

# Add and bring up the bridge
nmcli connection add type bridge con-name ${BRIDGE} ifname ${BRIDGE} ipv4.method disabled ipv6.method disabled
nmcli connection up ${BRIDGE}

# Add the VXLAN interface using ip link add
ip link add ${VXLAN_IFNAME} type vxlan id ${VXID} local ${LOCAL} group ${MCAST} dev ${PHYSICAL_IFACE} dstport 4789

# Bring up the VXLAN interface
ip link set ${VXLAN_IFNAME} up

# Add the VXLAN interface to the bridge
#bridge link set dev ${VXLAN_IFNAME} master ${BRIDGE}
ip link set dev vbeegfs743 master bbeegfs743

# Wait a moment to allow the interface to be fully initialized
sleep 2

# Verify that the VXLAN interface now exists
ip link show ${VXLAN_IFNAME} || echo "VXLAN interface ${VXLAN_IFNAME} not found"

# Display the forwarding database (FDB) table
bridge fdb show dev ${VXLAN_IFNAME}

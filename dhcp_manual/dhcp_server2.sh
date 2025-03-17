#!/bin/bash

#set -e  # Exit on failure

source variables.sh

# Function to clean up everything
clean_up() {
    echo "🧹 Cleaning up VXLAN and DHCP setup..."

    sudo virsh net-undefine ${VIRT_NETWORK}
    sudo virsh net-destroy ${VIRT_NETWORK}

    sudo nmcli connection delete ${INTERFACE} 

    sudo nmcli connection delete ${BRIDGE_NAME} 

    echo "✅ Cleanup complete!"
    exit 0
}

# Check for --clean flag
if [[ "$1" == "--clean" ]]; then
    clean_up
fi

sudo nmcli connection add type bridge con-name ${BRIDGE_NAME} ifname ${BRIDGE_NAME} ipv4.method disabled ipv6.method disabled

# this one seems to be peer-peer
#sudo nmcli connection add type vxlan slave-type bridge con-name ${VIRT_NETWORK} ifname ${INTERFACE} id 1 local ${DHCP_GATEWAY} remote 10.5.0.2 master ${BRIDGE_NAME}

# doesn't support the group parameter
#sudo nmcli connection add type vxlan slave-type bridge con-name ${VIRT_NETWORK} ifname ${INTERFACE} id 1 local ${LOCAL_IP} group ${MULTICAST_GROUP} dev ${DEV} master ${BRIDGE_NAME}

# instead of nmcli, use ip
sudo ip link add ${INTERFACE} type vxlan id 1 group ${MULTICAST_GROUP} dev ${DEV} dstport ${VXLAN_PORT}
sudo ip link set ${INTERFACE} up
sudo ip link set ${INTERFACE} master ${BRIDGE_NAME} 
sudo nmcli connection up ${BRIDGE_NAME}

LV_NET_XML="/tmp/${VIRT_NETWORK}.xml"  

cat <<EOF > "$LV_NET_XML"
<network>
    <name>${VIRT_NETWORK}</name>
    <forward mode="bridge" />
    <bridge name="${BRIDGE_NAME}" />
</network>
EOF

sudo virsh net-define ${LV_NET_XML} 
sudo virsh net-start ${VIRT_NETWORK} 
sudo virsh net-autostart  ${VIRT_NETWORK}
\rm $LV_NET_XML



#!/bin/bash

set -e  # Exit on failure

source variables.sh

# Function to clean up everything
clean_up() {
    echo "🧹 Cleaning up VXLAN and DHCP setup..."

    # Stop dnsmasq
    systemctl stop dnsmasq

    # Remove IP from bridge
    ip addr del ${DHCP_GATEWAY}/${DHCP_NETMASK} dev ${BRIDGE_NAME} 2>/dev/null || true

    # Bring down and delete the VXLAN interface
    ip link set ${VXLAN_NAME} down 2>/dev/null || true
    ip link del ${VXLAN_NAME} 2>/dev/null || true

    # Bring down and delete the bridge
    ip link set ${BRIDGE_NAME} down 2>/dev/null || true
    ip link del ${BRIDGE_NAME} 2>/dev/null || true

    # Remove dnsmasq configuration
    rm -f ${DNSMASQ_CONF}

    # Restart networking
    if systemctl list-units --type=service | grep -q "NetworkManager.service"; then
        echo "🔄 Restarting NetworkManager..."
        systemctl restart NetworkManager
    elif systemctl list-units --type=service | grep -q "systemd-networkd.service"; then
        echo "🔄 Restarting systemd-networkd..."
        systemctl restart systemd-networkd
    else
        echo "⚠️ No known networking service found to restart."
    fi


    echo "✅ Cleanup complete!"
    exit 0
}

# Check for --clean flag
if [[ "$1" == "--clean" ]]; then
    clean_up
fi

echo "🚀 Setting up VXLAN-based DHCP server..."

# Ensure necessary packages are installed
echo "📦 Installing required packages..."
dnf install -y dnsmasq iproute iputils

# Ensure the bridge exists before attaching anything
ip link show ${BRIDGE_NAME} >/dev/null 2>&1 || ip link add ${BRIDGE_NAME} type bridge
ip link set ${BRIDGE_NAME} up

# Create a single VXLAN interface
if ! ip link show ${VXLAN_NAME} >/dev/null 2>&1; then
    echo "🌐 Creating VXLAN interface: ${VXLAN_NAME}"
    ip link add ${VXLAN_NAME} type vxlan id ${VXLAN_ID} dev ${DEV} dstport ${VXLAN_PORT} group ${MULTICAST_GROUP}
    ip link set ${VXLAN_NAME} up
    ip link set ${VXLAN_NAME} master ${BRIDGE_NAME}
fi

# Assign an IP to the bridge (Only on the DHCP server)
echo "🌍 Assigning IP ${DHCP_GATEWAY} to ${BRIDGE_NAME}"
ip addr add ${DHCP_GATEWAY}/${DHCP_NETMASK} dev ${BRIDGE_NAME}

# Configure dnsmasq
echo "⚙️ Configuring dnsmasq for DHCP..."
cat > ${DNSMASQ_CONF} <<EOF
interface=${BRIDGE_NAME}
bind-interfaces
dhcp-range=${DHCP_RANGE_START},${DHCP_RANGE_END},${DHCP_NETMASK},12h
dhcp-option=3,${DHCP_GATEWAY}
dhcp-option=6,${DNS_SERVER}
EOF

# Restart dnsmasq
echo "🔄 Restarting dnsmasq..."
systemctl restart dnsmasq
systemctl enable dnsmasq

# Verify setup
echo "✅ VXLAN and DHCP setup complete!"
echo "Use '--clean' to remove this configuration."


#!/bin/bash

set -e  # Exit on failure

# Load variables
source ./variables.sh

# Function to clean up everything
clean_up() {
    echo "🧹 Cleaning up DHCP client setup..."

    # Bring down and delete the VXLAN interface
    ip link set ${VXLAN_NAME} down 2>/dev/null || true
    ip link del ${VXLAN_NAME} 2>/dev/null || true

    # Bring down and delete the bridge
    ip link set ${BRIDGE_NAME} down 2>/dev/null || true
    ip link del ${BRIDGE_NAME} 2>/dev/null || true

    # Restart the appropriate networking service
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

echo "🚀 Setting up VXLAN-based DHCP client..."

# Ensure necessary packages are installed
echo "📦 Installing required packages..."
dnf install -y iproute iputils dhclient

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

# Request a DHCP lease
echo "📡 Requesting a DHCP lease on ${BRIDGE_NAME}..."
sudo dhclient -v ${BRIDGE_NAME}

# Verify DHCP lease
echo "🔎 Checking assigned IP..."
ip addr show ${BRIDGE_NAME}

echo "✅ DHCP client setup complete! Use '--clean' to remove this configuration."


#!/bin/bash

# Script: install_ovs.sh
# Purpose: Install and configure Open vSwitch on a DNF-based system

# Exit immediately if a command exits with a non-zero status
set -e

# Function to check if python is available and is Python 2
check_python_version() {
    if ! command -v python &> /dev/null; then
        echo "Error: 'python' is not installed. Please install Python 2 and ensure it is accessible as 'python'."
        exit 1
    fi

    PYTHON_VERSION=$(python -c 'import sys; print(sys.version_info[0])')
    if [ "$PYTHON_VERSION" -ne 2 ]; then
        echo "Error: 'python' is not pointing to Python 2. Please install Python 2 and set it as 'python'."
        exit 1
    fi
}

# Run the Python version check
check_python_version

echo "Updating system and installing Open vSwitch dependencies..."

# Clone Open vSwitch repository
git clone https://github.com/openvswitch/ovs.git
cd ovs
#git checkout v2.7.0
git checkout v3.4.0

# Build Open vSwitch from source
./boot.sh
./configure
make
sudo make install

echo "Installed. Exiting"
exit 0

echo "Enabling and starting Open vSwitch service..."
sudo systemctl enable --now openvswitch

# Verify installation
echo "Checking Open vSwitch version..."
sudo ovs-vsctl --version

# Create a sample bridge (e.g., ovs-br1)
BRIDGE_NAME="ovs-br1"
echo "Creating Open vSwitch bridge: $BRIDGE_NAME"
sudo ovs-vsctl add-br $BRIDGE_NAME

# Optionally, assign an IP address to the bridge (adjust to your network setup)
# Example IP setup (for testing): sudo ip addr add 192.168.200.1/24 dev $BRIDGE_NAME
# Uncomment the line below and adjust as needed
# sudo ip addr add 192.168.200.1/24 dev $BRIDGE_NAME

# Bring up the bridge
echo "Bringing up the bridge interface..."
sudo ip link set dev $BRIDGE_NAME up

# Show current Open vSwitch configuration
echo "Current Open vSwitch configuration:"
sudo ovs-vsctl show

echo "Open vSwitch installation and basic bridge setup complete!"


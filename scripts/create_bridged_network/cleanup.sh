#!/bin/bash

# Source the variables file
source ./variables.sh

# Stop the libvirtd service
echo "Stopping libvirt service..."
sudo systemctl stop libvirtd

# Destroy and undefine the libvirt network (if it exists)
if virsh net-info "$LIBVIRT_NET_NAME" &>/dev/null; then
  echo "Destroying and undefining libvirt network: $LIBVIRT_NET_NAME"
  sudo virsh net-destroy "$LIBVIRT_NET_NAME"
  sudo virsh net-undefine "$LIBVIRT_NET_NAME"
fi

# Remove physical bridge (if it exists)
if sudo ip link show "$PHYSICAL_BRIDGE" &>/dev/null; then
  echo "Deleting physical bridge: $PHYSICAL_BRIDGE"
  sudo ip link set "$PHYSICAL_BRIDGE" down
  sudo brctl delbr "$PHYSICAL_BRIDGE"
fi

# Additional clean-up steps can be added here as needed

echo "Cleanup complete."


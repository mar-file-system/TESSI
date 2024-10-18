#!/bin/bash

# Source the variables file
source ./variables.sh

# Automatically detect the physical network interface that has an IP address
PHYSICAL_INTERFACE=$(ip -o -4 addr show | awk '{print $2}' | grep -v "lo" | head -n 1)

# Check if a physical interface was found
if [ -z "$PHYSICAL_INTERFACE" ]; then
  echo "No active physical network interface found with an IP address."
  exit 1
else
  echo "Detected physical network interface: $PHYSICAL_INTERFACE"
fi

# Check if the physical bridge already exists
if sudo ip link show "$PHYSICAL_BRIDGE" &>/dev/null; then
  echo "Physical bridge $PHYSICAL_BRIDGE already exists."
  exit 0
fi

# Check if the DHCP range is already in use
if ip route | grep -q "$DHCP_RANGE_START"; then
  echo "Error: The DHCP range $DHCP_RANGE_START is already in use. Please change the DHCP range in variables.sh and try again."
  exit 1
fi

# Create the physical bridge
echo "Creating physical bridge $PHYSICAL_BRIDGE..."
sudo brctl addbr "$PHYSICAL_BRIDGE"

# Bring up the physical bridge
echo "Bringing up the physical bridge..."
sudo ip link set "$PHYSICAL_BRIDGE" up

# Attach the physical network interface to the bridge
echo "Attaching $PHYSICAL_INTERFACE to $PHYSICAL_BRIDGE..."
sudo brctl addif "$PHYSICAL_BRIDGE" "$PHYSICAL_INTERFACE"

# Bring up the physical network interface
echo "Bringing up the physical interface $PHYSICAL_INTERFACE..."
sudo ip link set "$PHYSICAL_INTERFACE" up

# Assign the IP address from the physical interface to the bridge
echo "Assigning IP address to $PHYSICAL_BRIDGE..."
IP_ADDR=$(ip -o -f inet addr show "$PHYSICAL_INTERFACE" | awk '{print $4}')
sudo ip addr flush dev "$PHYSICAL_INTERFACE"
sudo ip addr add "$IP_ADDR" dev "$PHYSICAL_BRIDGE"

# Set a default route via the bridge, stripping the CIDR notation
IP_ONLY=${IP_ADDR%/*}
echo "Setting default route through $PHYSICAL_BRIDGE via $IP_ONLY..."
sudo ip route add default via "$IP_ONLY"

# Final confirmation with the assigned IP address
echo "Physical bridge $PHYSICAL_BRIDGE created, attached to $PHYSICAL_INTERFACE, and IP $IP_ADDR assigned."


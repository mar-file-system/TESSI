#!/bin/bash

# Source the variables file
source ./variables.sh

# Check if the virtual network already exists in libvirt
if virsh net-info "$LIBVIRT_NET_NAME" &>/dev/null; then
  echo "Virtual network $LIBVIRT_NET_NAME already exists in libvirt."
  exit 0
fi

# Define the XML for the virtual bridge network
VIRTUAL_NET_XML="/tmp/$LIBVIRT_NET_NAME.xml"

cat > "$VIRTUAL_NET_XML" <<EOF
<network>
  <name>$LIBVIRT_NET_NAME</name>
  <bridge name='$VIRTUAL_BRIDGE' stp='on' delay='0'/>
  <ip address='$DHCP_RANGE_START' netmask='$DHCP_SUBNET_MASK'>
    <dhcp>
      <range start='$DHCP_RANGE_START' end='$DHCP_RANGE_END'/>
    </dhcp>
  </ip>
</network>
EOF

# Define and start the virtual network in libvirt
echo "Creating and starting virtual network $LIBVIRT_NET_NAME using libvirt..."
sudo virsh net-define "$VIRTUAL_NET_XML"
sudo virsh net-start "$LIBVIRT_NET_NAME"
sudo virsh net-autostart "$LIBVIRT_NET_NAME"

# Cleanup temporary XML file
rm "$VIRTUAL_NET_XML"

echo "Virtual network $LIBVIRT_NET_NAME created and started in libvirt."




# Set variables (CHANGE ONLY IF NECESSARY)
VXLAN_ID=100
VXLAN_PORT=4789
BRIDGE_NAME="br-dhcp"
DEV="eno1"  # Change this if a different interface is used for communication
VXLAN_NAME="vxlan${VXLAN_ID}"
MULTICAST_GROUP="239.1.1.1"

# DHCP Server Config (CHANGE IF NEEDED)
DHCP_GATEWAY="192.168.100.1"
DHCP_NETMASK="255.255.255.0"
DHCP_RANGE_START="192.168.100.10"
DHCP_RANGE_END="192.168.100.100"
DNS_SERVER="8.8.8.8,8.8.4.4"

# File paths
DNSMASQ_CONF="/etc/dnsmasq.conf"

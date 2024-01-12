#!/bin/bash

# this is a script I created with chatgpt to do the bridge instructions
# at https://phoenixnap.com/kb/install-kvm-centos

# Delete the existing Ethernet interface connection
sudo nmcli connection delete eno1

# Create a new bridge interface 'br0'
sudo nmcli connection add type bridge autoconnect yes con-name br0 ifname br0

# Configure the bridge interface with your network settings
sudo nmcli connection modify br0 ipv4.addresses 172.16.0.15/24 ipv4.method manual
sudo nmcli connection modify br0 ipv4.gateway 172.16.0.254
sudo nmcli connection modify br0 ipv4.dns 8.8.8.8 +ipv4.dns 8.8.4.4

# Attach the network interface 'eno1' to the bridge
sudo nmcli connection add type bridge-slave autoconnect yes con-name eno1 ifname eno1 master br0

# Activate the new bridge interface
sudo nmcli connection up br0

# This script uses your IP address (172.16.0.15/24) and gateway (172.16.0.254).
# For DNS, I've used Google's public DNS servers (8.8.8.8 and 8.8.4.4) as
# placeholders. If you have specific DNS servers for your network, replace
# these with your actual DNS server addresses.

# Executing this script will reconfigure your network settings, so ensure you
# have direct access to the machine in case remote connectivity is lost.


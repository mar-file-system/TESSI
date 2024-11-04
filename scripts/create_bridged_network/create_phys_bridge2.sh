#!/bin/bash

# Function to get the current active Ethernet interface
get_active_interface() {
    ip -o link show | awk -F': ' '/state UP/ {print $2}' | grep -E '^e.*'
}

# Function to get the current IP address of the interface
get_current_ip() {
    local interface=$1
    ip addr show "$interface" | grep -w 'inet' | awk '{print $2}' | cut -d'/' -f1
}

# Function to check if br0 already exists
check_bridge_exists() {
    nmcli connection show br0 > /dev/null 2>&1
    return $?
}

# Function to check if the interface is already bridged
is_interface_in_bridge() {
    local interface=$1
    nmcli connection show "$interface" | grep "master: br0" > /dev/null 2>&1
    return $?
}

# Function to create and configure the bridge
create_bridge() {
    local ip_address=$1
    local last_octet=$(echo "$ip_address" | awk -F. '{print $4}')

    echo "Creating bridge br0 with IP 172.16.0.$last_octet"

    sudo nmcli connection add type bridge ifname br0 con-name br0
    sudo nmcli connection modify br0 ipv4.addresses "172.16.0.$last_octet/24"
    sudo nmcli connection modify br0 ipv4.gateway "172.16.0.254"
    sudo nmcli connection modify br0 ipv4.dns "8.8.8.8 8.8.4.4"
    sudo nmcli connection modify br0 ipv4.method manual
    sudo nmcli connection modify br0 bridge.stp yes
    sudo nmcli connection modify br0 bridge.priority 32768
}

# Function to add interface to the bridge
add_interface_to_bridge() {
    local interface=$1
    echo "Adding $interface to br0"
    sudo nmcli connection add type ethernet ifname "$interface" master br0
}

# Function to delete the independent interface connection if it exists
delete_independent_interface() {
    local interface=$1
    local conn_uuid=$(nmcli -g UUID connection show | grep "$interface")
    
    if [ -n "$conn_uuid" ]; then
        echo "Deleting independent connection for $interface (UUID: $conn_uuid)"
        sudo nmcli connection delete "$conn_uuid"
    else
        echo "No independent connection found for $interface."
    fi
}

# Main script logic

# Get the active Ethernet interface
active_interface=$(get_active_interface)

if [ -z "$active_interface" ]; then
    echo "Failed to identify the active Ethernet interface."
    exit 1
else
    echo "Active interface is $active_interface"
fi

# Get the current IP address of the active interface
current_ip=$(get_current_ip "$active_interface")

if [ -z "$current_ip" ]; then
    echo "Failed to retrieve the current IP address of $active_interface."
    exit 1
else
    echo "Current IP address of $active_interface is $current_ip"
fi

# Check if the br0 bridge already exists
if check_bridge_exists; then
    echo "Bridge br0 already exists, skipping creation."
else
    # Create and configure the bridge
    create_bridge "$current_ip"
fi

# Delete the independent interface connection if it exists
delete_independent_interface "$active_interface"

# Check if the interface is already in the bridge
if is_interface_in_bridge "$active_interface"; then
    echo "$active_interface is already bridged with br0, skipping."
else
    # Add the interface to the bridge
    add_interface_to_bridge "$active_interface"
fi

# Activate the bridge
sudo nmcli connection up br0


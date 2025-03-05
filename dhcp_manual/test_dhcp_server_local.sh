#!/bin/bash

set -e  # Exit on failure

# Load variables
source ./variables.sh

echo "🔍 Running local DHCP server tests..."

# Check if the bridge exists
echo "🔗 Checking if ${BRIDGE_NAME} exists..."
if ! ip link show ${BRIDGE_NAME} >/dev/null 2>&1; then
    echo "❌ Bridge ${BRIDGE_NAME} does not exist!"
    exit 1
fi
echo "✅ Bridge ${BRIDGE_NAME} is up."

# Check if VXLAN interface exists
echo "🌐 Checking if ${VXLAN_NAME} exists..."
if ! ip link show ${VXLAN_NAME} >/dev/null 2>&1; then
    echo "❌ VXLAN interface ${VXLAN_NAME} does not exist!"
    exit 1
fi
echo "✅ VXLAN interface ${VXLAN_NAME} is up."

# Check if dnsmasq is running
echo "🛠 Checking dnsmasq status..."
if ! systemctl is-active --quiet dnsmasq; then
    echo "❌ dnsmasq is not running!"
    exit 1
fi
echo "✅ dnsmasq is running."

# Check if dnsmasq is listening on the correct interface and port
echo "📡 Checking if dnsmasq is listening on ${BRIDGE_NAME}..."

if ! netstat -tulnp | grep -q "dnsmasq.*${BRIDGE_NAME}"; then
    echo "❌ WARN: dnsmasq is not listening on ${BRIDGE_NAME}!"
else
    echo "✅ dnsmasq is listening on ${BRIDGE_NAME}."
fi

# Check if the DHCP server is assigning IPs
echo "🔎 Checking DHCP leases..."
if [[ ! -s ${LEASES_FILE} ]]; then
    echo "⚠️ No active DHCP leases found. Try running a client test."
else
    echo "✅ Active DHCP leases detected:"
    cat ${LEASES_FILE}
fi

echo "🎯 All local DHCP server tests completed!"


#! /bin/env bash

set -e  # Exit immediately on error
set -x  # Echo each command

source variables.sh

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root. Please use sudo."
    exit 1
fi

# Check if the interface exists
if ip link show "$INTERFACE" > /dev/null 2>&1; then
    echo "Deleting interface $INTERFACE..."
    ip link delete "$INTERFACE"
    echo "Interface $INTERFACE deleted successfully."
else
    echo "Interface $INTERFACE does not exist. No action taken."
fi

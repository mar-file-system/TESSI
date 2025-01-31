#!/bin/bash
set -e

# Ensure the script is run with root privileges
if [ "$(id -u)" -ne 0 ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# Check for CentOS 8
OS_VERSION=$(grep -oP '(?<=VERSION_ID=")[^"]+' /etc/os-release)

if [[ "$OS_VERSION" != "8" ]]; then
    if [[ "$1" == "--force" ]]; then
        echo "Warning: TASSI has only been tested on CentOS 8. Proceeding anyway due to --force."
    else
        echo "Error: TASSI has only been tested on CentOS 8. Please either switch to CentOS 8 or use --force to proceed."
        exit 1
    fi
fi

echo "Updating system package list..."
dnf update -y

echo "Installing required system packages..."
dnf install -y $(cat installed_packages.txt)

# Detect Ansible's Python version dynamically
echo "Detecting Ansible's Python version..."
ANSIBLE_PYTHON=$(ansible-playbook --version | awk '/python version/ {print $NF}' | tr -d '[]')

if [ -z "$ANSIBLE_PYTHON" ]; then
    echo "Error: Could not determine Ansible's Python version!"
    exit 1
fi

echo "Ansible is using Python at: $ANSIBLE_PYTHON"

# Ensure this Python version is installed and set it as default
PYTHON_PATH=$(readlink -f $(which $ANSIBLE_PYTHON) || true)

if [ -n "$PYTHON_PATH" ]; then
    echo "Setting $ANSIBLE_PYTHON as the default Python3..."
    alternatives --set python3 "$PYTHON_PATH"
else
    echo "Warning: $ANSIBLE_PYTHON not found! Python3 may not be set correctly."
fi

echo "Installing required Python packages..."
$ANSIBLE_PYTHON -m pip install --upgrade pip
$ANSIBLE_PYTHON -m pip install -r requirements.txt

# Ensure WireGuard setup
echo "Setting up WireGuard..."
dnf install -y wireguard-tools elrepo-release epel-release
dnf --enablerepo=elrepo-kernel install -y kernel-ml
dnf install -y --allowerasing kernel-devel kernel-headers
echo "WireGuard setup complete."

echo "Checking kernel version..."
CURRENT_KERNEL=$(uname -r)
NEW_KERNEL=$(rpm -q kernel-ml --qf '%{VERSION}-%{RELEASE}.%{ARCH}\n' | tail -n 1)

if [[ "$CURRENT_KERNEL" != "$NEW_KERNEL" ]]; then
    echo "Kernel upgrade detected. Reboot is required."
    echo "Please manually reboot the system and re-run this script after rebooting."
    exit 1
else
    echo "Kernel is up-to-date."
fi

echo "Loading WireGuard kernel module..."
modprobe wireguard
if lsmod | grep -q wireguard; then
    echo "WireGuard module successfully loaded."
else
    echo "Error: WireGuard module failed to load!"
    exit 1
fi

echo "Setup complete."


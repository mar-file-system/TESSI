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

# Extract Python version from installed_packages.txt (e.g., python3.8)
PYTHON_PACKAGE=$(grep -E '^python[0-9]+\.[0-9]+' installed_packages.txt | head -n 1)

if [ -z "$PYTHON_PACKAGE" ]; then
    echo "Error: No Python version found in installed_packages.txt!"
    exit 1
fi

# Extract version number from the package name (e.g., 3.8 from python3.8)
PYTHON_VERSION=$(echo "$PYTHON_PACKAGE" | grep -oP '[0-9]+\.[0-9]+')

# Set ANSIBLE_PYTHON and PYTHON_PATH
ANSIBLE_PYTHON="python${PYTHON_VERSION}"
PYTHON_PATH=$(readlink -f "$(which $ANSIBLE_PYTHON)" || true)

if [ -n "$PYTHON_PATH" ]; then
    echo "Setting $ANSIBLE_PYTHON ($PYTHON_PATH) as the default Python3..."
    sudo alternatives --set python3 "$PYTHON_PATH"
else
    echo "Warning: $ANSIBLE_PYTHON not found! Python3 may not be set correctly."
    exit 1
fi

# Install required Python packages using the detected Python version
echo "Installing required Python packages with $ANSIBLE_PYTHON..."
$ANSIBLE_PYTHON -m ensurepip --upgrade
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


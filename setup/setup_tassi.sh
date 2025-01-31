#!/bin/bash
set -e

# Ensure the script is run with root privileges
if [ "$(id -u)" -ne 0 ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# Ensure package list exists
if [ ! -f installed_packages.txt ] || [ ! -f requirements.txt ]; then
    echo "Error: installed_packages.txt or requirements.txt not found!"
    exit 1
fi

echo "Updating system package list..."
dnf update -y

echo "Installing required system packages..."
dnf install -y $(cat installed_packages.txt)

echo "Detecting Ansible's Python version..."
ANSIBLE_PYTHON=$(ansible-playbook --version | awk '/python version/ {print $NF}' | tr -d '[]')

if [ -z "$ANSIBLE_PYTHON" ]; then
    echo "Error: Could not determine Ansible's Python version!"
    exit 1
fi

echo "Ansible is using Python at: $ANSIBLE_PYTHON"

# Ensure this Python version is installed
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

echo "Setup complete."


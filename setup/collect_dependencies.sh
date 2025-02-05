#!/bin/bash
set -e

# Capture system packages
dnf list installed | awk '{print $1}' | grep -i Installed > installed_packages.txt

# Detect Ansible's Python version dynamically
echo "Detecting Ansible's Python version..."
ANSIBLE_PYTHON=$(ansible-playbook --version | awk -F= '/python version/ {print $2}' | awk '{print $1}')

if [ -z "$ANSIBLE_PYTHON" ]; then
    echo "Error: Could not determine Ansible's Python version!"
    exit 1
fi

echo "Ansible is using Python at: $ANSIBLE_PYTHON"

# Ensure Ansible's Python is included in installed_packages.txt
# Extract the major.minor version (e.g., 3.8 from 3.8.18)
ANSIBLE_PYTHON_VERSION=$(echo $ANSIBLE_PYTHON | awk -F. '{print $1"."$2}')
PYTHON_PACKAGE="python${ANSIBLE_PYTHON_VERSION}"

if ! grep -q "$PYTHON_PACKAGE" installed_packages.txt; then
    echo "$PYTHON_PACKAGE" >> installed_packages.txt
fi

# Use the right pip version for Ansible's Python
# Find pip path associated with Ansible's Python
ANSIBLE_PIP=$($ANSIBLE_PYTHON -m pip --version 2>/dev/null | awk '{print $1}')

# Fallback to pip3.8 if Ansible's Python pip is not found
if [ -z "$ANSIBLE_PIP" ]; then
    echo "Warning: Could not find pip for $ANSIBLE_PYTHON, defaulting to pip3.8"
    ANSIBLE_PIP="pip3.8"
fi

# Capture installed Python packages
$ANSIBLE_PIP freeze > requirements.txt

# Git commit the updated dependency lists
git add installed_packages.txt requirements.txt
git commit -m "Adding TASSI requirements and dependencies"
git push


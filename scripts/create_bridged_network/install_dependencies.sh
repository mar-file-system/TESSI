#!/bin/bash

# Source the variables file
source ./variables.sh

# Array of packages needed for the setup
PACKAGES=(
  "libvirt-daemon"
  "libvirt-daemon-config-network"
  "libvirt-daemon-kvm"
  "bridge-utils"
  "dnsmasq"
)

# Loop through the array and install each package
for package in "${PACKAGES[@]}"; do
  if ! dnf list installed "$package" &>/dev/null; then
    echo "Installing $package..."
    sudo dnf install -y "$package"
  else
    echo "$package is already installed."
  fi
done

echo "All dependencies installed."


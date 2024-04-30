#!/bin/bash

# Ensure the script is run with root privileges
if [ "$(id -u)" -ne 0 ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# Update system
echo "Updating system..."
dnf update -y

# Enable necessary modules
echo "Enabling necessary DNF modules..."
dnf module enable javapackages-runtime:201801 -y
dnf module enable llvm-toolset:rhel8 -y
dnf module enable perl:5.26 -y
dnf module enable perl-IO-Socket-SSL:2.066 -y
dnf module enable perl-libwww-perl:6.34 -y
dnf module enable python36:3.6 -y
dnf module enable python38:3.8 -y
dnf module enable virt:rhel -y

# Install necessary modules
echo "Installing necessary DNF modules..."
dnf module install javapackages-runtime:201801 -y
dnf module install llvm-toolset:rhel8 -y
dnf module install perl:5.26 -y
dnf module install perl-IO-Socket-SSL:2.066 -y
dnf module install perl-libwww-perl:6.34 -y
dnf module install python36:3.6 -y
dnf module install python38:3.8 -y
dnf module install virt:rhel -y

echo "DNF module setup complete."

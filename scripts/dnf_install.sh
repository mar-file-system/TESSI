#!/bin/bash

# Ensure the script is run with root privileges
if [ "$(id -u)" -ne 0 ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# Update system
echo "Updating system..."
dnf update -y

# Enable and install necessary modules
echo "Enabling and installing necessary DNF modules..."

# Java packages runtime utilities
dnf module enable javapackages-runtime:201801 -y
dnf module install javapackages-runtime:201801 -y

# LLVM toolset
dnf module enable llvm-toolset:rhel8 -y
dnf module install llvm-toolset:rhel8 -y

# Perl and its related packages
dnf module enable perl:5.26 -y
dnf module install perl:5.26 -y

dnf module enable perl-IO-Socket-SSL:2.066 -y
dnf module install perl-IO-Socket-SSL:2.066 -y

dnf module enable perl-libwww-perl:6.34 -y
dnf module install perl-libwww-perl:6.34 -y

# Python versions
dnf module enable python36:3.6 -y
dnf module install python36:3.6 -y

dnf module enable python38:3.8 -y
dnf module install python38:3.8 -y

# Virtualization tools
dnf module enable virt:rhel -y
dnf module install virt:rhel -y

# Install all necessary DNF packages from a list
echo "Installing all necessary DNF packages from file..."
while IFS= read -r line; do
    package=$(echo $line | awk '{print $1}')  # Extracting only the package name
    dnf install "$package" -y
done < installed_packages.txt  # Skip the first two lines (header)

echo "DNF module and package setup complete."


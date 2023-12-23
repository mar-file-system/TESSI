#! /usr/bin/bash

if [ "$(id -u)" != "0" ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

iso_path="/path/to/Rocky-8.9-x86_64-minimal.iso"
iso_url="https://download.rockylinux.org/pub/rocky/8/isos/x86_64/Rocky-8.9-x86_64-minimal.iso"

# Check if the ISO file exists
if [ ! -f "$iso_path" ]; then
    echo "ISO file not found. Downloading from $iso_url..."
    wget -O "$iso_path" "$iso_url"
fi

# Define VM parameters
vm_name="tassi01"
memory=2048
cpus=2
disk_size=6

# Create VM
virt-install \
--name "$vm_name" \
--ram "$memory" \
--vcpus "$cpus" \
--disk path=/var/lib/libvirt/images/"$vm_name".img,size="$disk_size" \
--os-type linux \
--os-variant centos8 \
--network network=default \
--graphics none \
--console pty,target_type=serial \
--location "$iso_path" \
--extra-args 'console=ttyS0'


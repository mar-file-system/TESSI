#! /usr/bin/bash

if [ "$(id -u)" != "0" ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

iso_url="https://download.rockylinux.org/pub/rocky/8/isos/x86_64/Rocky-8.9-x86_64-minimal.iso"
iso_url="http://abqix.mm.fcix.net/centos/8-stream/isos/x86_64/CentOS-Stream-8-20231218.0-x86_64-boot.iso"

filename=$(basename "$iso_url")
iso_path="/var/lib/libvirt/images/$filename"

# Check if the ISO file exists
if [ ! -f "$iso_path" ]; then
    echo "ISO file not found. Downloading from $iso_url..."
    wget -O "$iso_path" "$iso_url"
    chmod 0755 $iso_path
fi

# Define VM parameters
vm_name="tassi01"
memory=2048
cpus=2
disk_size=6

location="http://mirror.centos.org/centos/8-stream/BaseOS/x86_64/os/"

# Create VM, we were using iso_path as the argument to --location but let's try to do a network install now
# --location "$iso_path" \
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
--location "$location" \
--extra-args 'console=ttyS0'





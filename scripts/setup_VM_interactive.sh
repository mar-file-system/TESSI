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
    echo "ISO file not found. NOT Downloading from $iso_url..."
    #wget -O "$iso_path" "$iso_url"
    chmod 0755 $iso_path
fi

# Define VM parameters
vm_name="testdnf"
memory=4096
cpus=2
disk_size=12

location="http://mirror.centos.org/centos/8-stream/BaseOS/x86_64/os/"
location="https://repo.almalinux.org/almalinux/8.10/isos/x86_64/AlmaLinux-8.10-x86_64-minimal.iso"
location="/var/lib/libvirt/images/AlmaLinux-8.10-x86_64-minimal.iso"
osvar="almalinux8"
location="https://download.fedoraproject.org/pub/fedora/linux/releases/40/Everything/x86_64/os"
osvar="fedora31"

# cleanup any old ones
virsh destroy $vm_name
virsh undefine $vm_name
rm -f /var/lib/libvirt/images/$vm_name.img

# Create VM, we were using iso_path as the argument to --location but let's try to do a network install now
# --location "$iso_path" \
echo virt-install \
--name "$vm_name" \
--ram "$memory" \
--vcpus "$cpus" \
--disk path=/var/lib/libvirt/images/"$vm_name".img,size="$disk_size" \
--os-type linux \
--os-variant $osvar \
--network network=default \
--graphics none \
--console pty,target_type=serial \
--location "$location" \
--extra-args 'console=ttyS0'

# choose text mode
# then choose 8 to do root password
# then choose 4 to switch to minimal install
# refresh if necessary to make sure installation source (#3) is good, then begin
# for installation destination, choose 'Use All Space' and option 2 'LVM' 
# set up time and use 0.pool.ntp.org 

# would be good to also copy the ssh key to it and get the IP address somehow



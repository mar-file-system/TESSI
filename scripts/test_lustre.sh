#!/bin/bash

# Get the primary IP address
IP_ADDRESS=$(hostname -I)

# Set the hostname 
hname=mylustrehost
hostnamectl set-hostname $hname 

# also update /etc/hosts with this new hostname
echo "$IP_ADDRESS $hname" >> /etc/hosts

FSTYPE=zfs ./lustre/tests/llmount.sh

df -h /mnt/lustre
./lustre/utils/lfs getstripe /mnt/lustre/
./lustre/utils/lfs setstripe -c -1 /mnt/lustre
./lustre/utils/lfs getstripe /mnt/lustre/

dd if=/dev/zero of=/mnt/lustre/file.out bs=1MB count=400


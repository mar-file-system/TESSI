#!/bin/bash

testfile=/mnt/lustre/file.out

# Get the primary IP address
IP_ADDRESS=$(hostname -I)

# Set the hostname 
# not necessary anymore since the VM creation tools handle this
# hname=mylustrehost
# hostnamectl set-hostname $hname 

# also update /etc/hosts with this new hostname
# hmmm, I wonder if this is necessary?
echo "No longer setting the hostname in /etc/hosts, is that a problem?"
# echo "$IP_ADDRESS $hname" >> /etc/hosts

# first clean it up in case we forgot to do that
./lustre/tests/llmountcleanup.sh
\rm -rf /mnt/lustre

FSTYPE=zfs ./lustre/tests/llmount.sh

df -h /mnt/lustre
./lustre/utils/lfs getstripe /mnt/lustre/
dd if=/dev/zero of=$testfile bs=1MB count=400
df -h /mnt/lustre-*
\rm $testfile

# change striping behavior, 
# write a large file and then check it was striped across all osts
./lustre/utils/lfs setstripe -c -1 /mnt/lustre
./lustre/utils/lfs getstripe /mnt/lustre/

dd if=/dev/zero of=$testfile bs=1MB count=400
df -h /mnt/lustre-*
\rm $testfile

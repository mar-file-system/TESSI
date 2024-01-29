#!/bin/bash

LLMOUNT="./lustre/tests/llmount.sh"
[ ! -f "$LLMOUNT_SH" ] && { echo "Warning: $LLMOUNT_SH does not exist."; exit 1; }
[ "$(id -u)" -ne 0 ] && { echo "Warning: This script must be run as root."; exit 1; }

testfile=/mnt/lustre/file.out

# first clean it up in case we forgot to do that
\rm -rf /mnt/lustre

FSTYPE=zfs $LLMOUNT 

# test the default striping behavior
df -h /mnt/lustre
./lustre/utils/lfs getstripe /mnt/lustre/
dd if=/dev/zero of=$testfile bs=1MB count=400
echo "The default striping pattern"
df -h /mnt/lustre-*
\rm $testfile

# change striping behavior, 
# write a large file and then check it was striped across all osts
./lustre/utils/lfs setstripe -c -1 /mnt/lustre
./lustre/utils/lfs getstripe /mnt/lustre/

dd if=/dev/zero of=$testfile bs=1MB count=400
echo "The modified striping pattern"
df -h /mnt/lustre-*
\rm $testfile

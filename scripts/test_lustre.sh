#!/bin/bash

cd /usr/local/src/lustre-release

LLMOUNT="./lustre/tests/llmount.sh"
LLMOUNT_CLEANUP="./lustre/tests/llmountcleanup.sh"

[ ! -f "$LLMOUNT" ] && { echo "Warning: $LLMOUNT does not exist."; exit 1; }
[ "$(id -u)" -ne 0 ] && { echo "Warning: This script must be run as root."; exit 1; }

test_striping() {
    FILESIZE_MB=200
    testfile=/mnt/lustre/file.out
    dd if=/dev/zero of=$testfile bs=1MB count=$FILESIZE_MB
    sleep 10
    stripes=`df -h /mnt/lustre-ost* | grep -v Filesystem | awk '{print $3}' | tr '\n' ' '`
    echo "Stripes with $1 pattern: $stripes"
    rm $testfile
    sleep 10
}

# first clean it up in case we forgot to do that
$LLMOUNT_CLEANUP

FSTYPE=zfs $LLMOUNT 

# test the default striping behavior
df -h /mnt/lustre
./lustre/utils/lfs getstripe /mnt/lustre/
test_striping "default"

# change striping behavior, 
./lustre/utils/lfs setstripe -c -1 /mnt/lustre
./lustre/utils/lfs getstripe /mnt/lustre/

test_striping "modified"

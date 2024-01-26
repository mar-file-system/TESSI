#! /usr/bin/env bash

baseimage='freshinstall'
sleeptime=2
listvms='./list_vms.py'

[[ $(id -u) -ne 0 ]] && { echo "Warning: This script must be run as root"; exit 1; }
[[ -x "$listvms" ]] || { echo "Warning: $listvms is not an executable"; exit 1; }

shutdown_vm_and_wait() {
    local vm_name="$1"
    
    # Check if the VM is running
    if [[ "$(virsh domstate $vm_name)" != "running" ]]; then
        return 1
    fi

    # Initiate shutdown
    virsh shutdown "$vm_name"
    if [ $? -ne 0 ]; then
        echo "Failed to initiate shutdown for $vm_name"
        return 1
    fi

    # Wait for the VM to shut down
    echo "Waiting for $vm_name to shut down..."
    while [[ "$(virsh domstate $vm_name)" != "shut off" ]]; do
        sleep $sleeptime
    done

    echo "$vm_name has been shut down."
}

set_hostname() {
    local vm_name="$1"

    # was doing this with virt-sysprep but that was purging a bunch of other stuff
    #virt-sysprep --hostname $vm -d $vm

    # now do it by mounting the disk image and manually overriding the file content
    mpoint=/tmp/mnt/vm_disk.$$
    mkdir -p $mpoint 

    vmimage=`virsh domblklist $vm_name | grep vda | awk '{print $2}'`
    guestmount -a $vmimage -i $mpoint
    hfile=$mpoint/etc/hostname
    [[ -e "$hfile" ]] || { echo "Warning: $hfile not found"; exit 1; }
    echo $vm_name > $hfile
    guestunmount $mpoint

    echo "Set hostname to be $vm_name"
}

baseavailable=`$listvms | grep -q $baseimage`
if $baseavailable; then
  shutdown_vm_and_wait $baseimage
fi

hname=`hostname`

for i in {01..05}; do
  vm="${hname}vm$i"
  if $listvms | grep -q $vm; then
    echo "Need to clean up $vm"
    shutdown_vm_and_wait $vm
    # List all snapshots for the VM and iterate through them
    for snapshot in $(virsh snapshot-list --name $vm); do
      echo "Deleting snapshot: $vm:$snapshot"
      virsh snapshot-delete "$vm" "$snapshot"
    done
  fi
  virsh undefine $vm --remove-all-storage --snapshots-metadata
  sleep $sleeptime

  if $baseavailable; then
   echo "Need to clone from $baseimage"
   virt-clone --original $baseimage --name $vm --auto-clone --nonsparse
   sleep $sleeptime
   set_hostname $vm
   sleep $sleeptime
   virsh start $vm
  fi
done

echo All done.
$listvms

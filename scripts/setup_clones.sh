#! /usr/bin/env bash

baseimage='freshinstall'
sleeptime=2
listvms='./list_vms.py'

baseavailable=`$listvms | grep -q $baseimage`
if $baseavailable; then
  virsh shutdown $baseimage
fi

[[ $(id -u) -ne 0 ]] && { echo "Warning: This script must be run as root"; exit 1; }
[[ -x "$listvms" ]] || { echo "Warning: $listvms is not an executable"; exit 1; }

hname=`hostname`

for i in {01..05}; do
  vm="${hname}vm$i"
  if $listvms | grep -q $vm; then
    echo "Need to clean up $vm"
    virsh shutdown $vm
    sleep $sleeptime
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
   virt-clone --original $baseimage --name $vm --auto-clone 
   sleep $sleeptime
   virt-sysprep --hostname $vm -d $vm
   sleep $sleeptime
   virsh start $vm
  fi
done

echo All done.
$listvms

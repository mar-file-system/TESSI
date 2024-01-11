#! /usr/bin/bash


vm_name="tassi01"
snap="centos8streamsnap"
snap="passwordless_ssh"
snap="git_installed"
snap="ansible_ready"

if [ "$(id -u)" != "0" ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

sudo virsh shutdown $vm_name
while [ "$(sudo virsh domstate tassi01)" != "shut off" ]; do
    sleep 1
done
sudo virsh snapshot-revert --domain $vm_name --snapshotname $snap
sudo virsh start $vm_name

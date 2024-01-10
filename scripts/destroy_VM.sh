#! /usr/bin/bash


vm_name="tassi01"

if [ "$(id -u)" != "0" ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

virsh destroy tassi01
virsh undefine tassi01
rm /var/lib/libvirt/images/tassi01.img

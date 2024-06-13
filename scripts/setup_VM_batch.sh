#! /usr/bin/bash

USAGE="USAGE: $0 hostname [must be run as root]"
if [ "$(id -u)" != "0" ] || [ $# -eq 0 ]; then
    echo $USAGE
    exit 1
else
    hostname=$1
fi

# Define VM parameters
memory=4096
cpus=2
disk_size=12
iso_path="/var/lib/libvirt/images/AlmaLinux-8.10-x86_64-minimal.iso"
ios_path="/var/lib/libvirt/boot/AlmaLinux-8.10-x86_64-minimal.iso"
root_password="password"
ssh_pub=$(cat /home/jbent/.ssh/authorized_keys)

# Prepare kickstart file and chdir to the directory where we create it
ks_dir="kickstart_files"
ks_file="$hostname.kickstart"
mkdir -p $ks_dir

# Embed and customize the kickstart template
cat <<EOF > $ks_dir/$ks_file 
#version=RHEL8
text
%packages
@^minimal-environment
kexec-tools
%end
lang en_US.UTF-8
network  --bootproto=dhcp --device=enp1s0 --nameserver=8.8.8.8,8.8.4.4 --ipv6=auto --activate
network  --hostname=$hostname
cdrom
firstboot --enable
skipx
ignoredisk --only-use=vda
bootloader --append="crashkernel=auto" --location=mbr --boot-drive=vda
autopart
clearpart --all --initlabel --drives=vda
timezone America/New_York --isUtc
rootpw --plaintext ${root_password}
%addon com_redhat_kdump --enable --reserve-mb='auto'
%end
%anaconda
pwpolicy root --minlen=6 --minquality=1 --notstrict --nochanges --notempty
pwpolicy user --minlen=6 --minquality=1 --notstrict --nochanges --emptyok
pwpolicy luks --minlen=6 --minquality=1 --notstrict --nochanges --notempty
%end
%post
mkdir -p /root/.ssh
chmod 700 /root/.ssh
echo "${ssh_pub}" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
shutdown -P now
%end
EOF

# install the VM
virt-install \
--name "$hostname" \
--ram "$memory" \
--vcpus "$cpus" \
--disk path=/var/lib/libvirt/images/"$hostname".img,size="$disk_size" \
--os-type linux \
--os-variant almalinux8 \
--network network=default \
--graphics none \
--initrd-inject "$ks_dir/$ks_file" \
--location "$iso_path" \
--noreboot \
--wait 20 \
--noautoconsole \
--extra-args "inst.ks=file:/$ks_file console=tty0 console=ttyS0,115200n8" < /dev/null

virsh shutdown $hostname
sleep 60

# start the VM
virsh start $hostname

# clear out any old hostnames
ssh-keygen -R $hostname

echo "$hostname should be booting now."


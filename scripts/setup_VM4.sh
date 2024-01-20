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
centos8="http://mirror.centos.org/centos/8-stream"
baseos_location="$centos8/BaseOS/x86_64/os/"
appstr_location="$centos8/AppStream/x86_64/os/"
root_password="password"

# Prepare kickstart file and chdir to the directory where we create it
ks_dir="kickstart_files"
ks_file=hostname.kickstart
mkdir -p $ks_dir

# Embed and customize the kickstart template
cat <<EOF > $ks_dir/$ks_file 
#version=RHEL8
text
repo --name="AppStream" --baseurl=${appstream_location}
%packages
@^minimal-environment
kexec-tools
%end
lang en_US.UTF-8
network  --hostname=$hostname
url --url="${baseos_location}"
firstboot --enable
skipx
ignoredisk --only-use=vda
bootloader --append="crashkernel=auto" --location=mbr --boot-drive=vda
autopart
clearpart --all --initlabel --drives=vda
timezone US/Mountain --isUtc --ntpservers=0.pool.ntp.org,1.pool.ntp.org,2.pool.ntp.org,3.pool.ntp.org
rootpw --plaintext ${root_password}
%addon com_redhat_kdump --enable --reserve-mb='auto'
%end
%anaconda
pwpolicy root --minlen=6 --minquality=1 --notstrict --nochanges --notempty
pwpolicy user --minlen=6 --minquality=1 --notstrict --nochanges --emptyok
pwpolicy luks --minlen=6 --minquality=1 --notstrict --nochanges --notempty
%end
%post
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
--os-variant centos8 \
--network network=default \
--graphics none \
--initrd-inject "$ks_dir/$ks_file" \
--location "$baseos_location" \
--noreboot \
--noautoconsole \
--wait 15
--extra-args "inst.ks=file:/$ks_file console=ttyS0,115200n8" < /dev/null

#--console pty,target_type=serial \

# --extra-args "console=ttyS0 ks=http://$web_server_ip:$web_server_port/$hostname.kickstart" \

# start the VM
virsh shutdown $hostname
sleep 10
virsh start $hostname

echo "$hostname should be installed now. Run ssh-copy-id when complete to allow passwordless ssh"

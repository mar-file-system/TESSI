#! /usr/bin/bash

USAGE="$0 hostname [must be run as root]"
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
ip=`hostname -I | awk '{print $1}'`
root_password="password"

# Function to find an available port
find_available_port() {
    for port in $(seq 8000 8100); do
        echo > /dev/tcp/localhost/$port
        if [ $? -ne 0 ]; then
            echo $port
            return
        fi
    done
    echo "No available port found" >&2
    exit 1
}

# Prepare kickstart file
ks_dir="kickstart_files"
mkdir -p $ks_dir
cd $ks_dir

# Embed and customize the kickstart template
cat <<EOF > $hostname.kickstart
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
EOF

# Start a web server on an available port
available_port=$(find_available_port)
python3 -m http.server $available_port &

# Store web server PID to kill it later
web_server_pid=$!

virt-install \
--name "$hostname" \
--ram "$memory" \
--vcpus "$cpus" \
--disk path=/var/lib/libvirt/images/"$hostname".img,size="$disk_size" \
--os-type linux \
--os-variant centos8 \
--network network=default \
--graphics none \
--console pty,target_type=serial \
--location "$baseos_location" \
--extra-args 'console=ttyS0 ks=http://$ip:$available_port/$hostname.kickstart'

# Kill the web server
kill $web_server_pid

echo "$hostname should be installed now. Run ssh-copy-id to allow passwordless ssh"

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
web_server_ip=`hostname -I | awk '{print $1}'`
root_password="password"

# Prepare kickstart file and chdir to the directory where we create it
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

# Function to start web server on first available port
start_web_server() {
    local port=8000

    while true; do
        # Try to start the server in the background
        python3 -m http.server $port --bind $web_server_ip &>/dev/null &
        local pid=$!

        # Wait a moment to see if the server starts successfull
        sleep 2

        # Check if the process is still running
        if ps -p $pid > /dev/null; then
            echo $port
            return
        else
            # If not running, assume it's because it couldn't find a port so try the next port
            ((port++))
        fi

        # Check if port range exceeded
        if [ $port -gt 8100 ]; then
            echo "No available port found" >&2
            exit 1
        fi
    done
}

# Start web server and get the allocated port and the child PID
web_server_port=$(start_web_server)
web_server_pid=$!

echo "Web server is now running on $web_server_ip:$web_server_port"

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
--extra-args "console=ttyS0 ks=http://$web_server_ip:$web_server_port/$hostname.kickstart" \
--noautoconsole \
--wait -1

# Kill the web server
kill $web_server_pid

echo "$hostname should be installed now. Run ssh-copy-id to allow passwordless ssh"

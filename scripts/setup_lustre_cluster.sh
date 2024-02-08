#! /usr/bin/bash

if [ "$(id -u)" != "0" ] ; then
    echo "Must be run as root" 
    exit 1
fi

base_vm='freshinstall'
base_lustre='lustrebase'
network_name="hostonly-net"
network_file="/tmp/$$"
mac_addresses=""

check_vm_status() {
  local vm_name="$1"
  # Check if the VM exists
  if ! virsh list --all | grep -q "$vm_name"; then
    echo "VM $vm_name does not exist."
    return 1
  fi

  # Check if the VM is shut off
  if virsh list --all --state-shutoff | grep -q "$vm_name"; then
    return 0
  else
    echo "VM $vm_name exists but is not shut off."
    return 2
  fi
}

if ! check_vm_status "$base_vm"; then
  echo "Warning: VM does not exist or is not shut off."
  exit 1
fi

# Function to check if the specified network exists in the output of 'sudo virsh net-list --all'
check_network_exists() {
    local network_name=$1
    if virsh net-list --all | grep -q "$network_name"; then
        return 0  # Success, network exists
    else
        return 1  # Failure, network does not exist
    fi
}

function setup_hostonly_network() {
    local network_file=$1
    local mac_addresses=$2
    local network_name=$3

    if check_network_exists "$network_name"; then
        echo "Network '$network_name' exists. Cleaning it up."
        for op in 'destroy' 'undefine'
        do
            virsh net-$op $network_name
            sleep 2
        done
    fi

    echo "Setting up hostonly network"
    cat <<EOF > "$network_file"
<network>
  <name>$network_name</name>
  <bridge name="virbr1" stp="on" delay="0"/>
  <ip address="192.168.56.1" netmask="255.255.255.0">
    <dhcp>
      <range start="192.168.56.2" end="192.168.56.254"/>
      <!-- Static IP assignment -->
      $mac_addresses
      <!-- Add more <host> elements for other VMs as needed -->
    </dhcp>
  </ip>
</network>
EOF

    virsh net-define $network_file
    virsh net-start $network_name
    virsh net-autostart $network_name
    virsh net-list --all | grep $network_name 
}

setup_hostonly_network $network_file "$mac_addresses" $network_name

# now create the first base clone
if virsh list --all | grep -q "$base_lustre"; then
    echo "Clean up old base lustre image $base_lustre"
      if virsh list --all --state-running | grep -q "$base_lustre"; then
        virsh destroy $base_lustre
      fi
    virsh undefine $base_lustre --remove-all-storage --snapshots-metadata
fi
virt-clone --original $base_vm --name $base_lustre --auto-clone --nonsparse

add_nic_to_vm() {
  local vm_name="$1"
  local network_name="$2" # Change this to your desired network
  # Generate a random MAC address with the second nibble set to one of 2, 6, A, or E to ensure it's unicast and locally administered
  local mac_address="02:$(openssl rand -hex 5 | sed 's/\(..\)/\1:/g; s/.$//')"

  # Ensure the VM is not running
  virsh domstate "$vm_name" | grep -i running &> /dev/null && {
    echo "Please shut down the VM before adding a NIC."
    return 1
  }

  # Add a new network interface to the VM's XML configuration
  virsh dumpxml "$vm_name" > "${vm_name}.xml"
  sed -i "/<\/devices>/i \
  <interface type='network'>\n\
    <mac address='${mac_address}'/>\n\
    <source network='${network_name}'/>\n\
    <model type='virtio'/>\n\
  </interface>" "${vm_name}.xml"

  # Re-define the VM with the updated XML
  virsh define "${vm_name}.xml" > /dev/null # silence since we are using echo to assign a variable in the caller

  # Cleanup: Remove the temporary XML file
  rm -f "${vm_name}.xml"

  # Return the MAC address of the newly added network interface
  echo "${mac_address}"
}

mac_addr=$(add_nic_to_vm "$base_lustre" "$network_name")
ip_addr="192.168.56.101"
echo "Got $mac_addr for $base_lustre - will assign $ip_addr"

mac_addresses="${mac_addresses}     <host mac=\"${mac_addr}\" name=\"${base_lustre}\" ip=\"${ip_addr}\"/>"
echo "Now mac_addresses is $mac_addresses"
setup_hostonly_network $network_file "$mac_addresses" $network_name

systemctl restart virtlogd.socket
systemctl restart libvirtd
virsh start $base_lustre


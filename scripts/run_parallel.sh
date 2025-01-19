#! /bin/bash -e

CREATE_WG=wireguard
CREATE_VMS=opentofu/dynamic_hosts_libvirt_vms/
CREATE_GRAPH=network_graph
DEBUG_NETWORK=network_graph

phase() {
  local message="$1"
  local length=${#message}
  local border=$(printf '#%.0s' $(seq 1 $((length + 10))))
  
  echo
  echo "$border"
  echo "#####  $message  #####"
  echo "$border"
  echo
}

phase "Starting Parallel Run of TASSI"

phase "Cleaning up VMs"
pushd .
cd $CREATE_VMS
sudo tofu destroy --auto-approve
popd

phase "Cleaning up Networking"
pushd .
cd $CREATE_WG
sudo ansible-playbook -i inventory.yaml create_wireguard_tunnels.yaml --tags cleanup
popd

phase "Clean up Artifacts"
pushd . 
cd $CREATE_GRAPH
sudo \rm -f artifacts/*png
popd

phase "Create Networking and Tofu System Description"
pushd .
cd $CREATE_WG
sudo ansible-playbook -i inventory.yaml create_wireguard_tunnels.yaml 
popd

phase "Create VMs Using the Auto-Generated Tofu System Description"
pushd .
cd $CREATE_VMS
sudo cp /tmp/system_description.tf .
sudo tofu apply --auto-approve
popd

phase "Manually add Routes. TODO: Automate this somehow"
# VMs on in07
for vm in beegfs-meta00 beegfs-client01 beegfs-client00; do
  #ssh in07 "ssh -o StrictHostKeyChecking=no root@$vm 'ip route add 192.68.2.0/24 via 192.68.3.1'"
  echo "Not manually adding route to $vm. Hoping this is done automatically in kickstart"
done

# VMs on in16
for vm in beegfs-meta01 beegfs-data00 beegfs-data01; do
  #ssh in16 "ssh -o StrictHostKeyChecking=no root@$vm 'ip route add 192.68.2.0/24 via 192.68.3.33'"
  echo "Not manually adding route to $vm. Hoping this is done automatically in kickstart"
done


phase "Create Network Graph"
pushd .
cd $CREATE_GRAPH
sudo ansible-playbook -i inventory.yaml make_network_graph.yaml 
popd

phase "Debug Network"
pushd .
cd $CREATE_GRAPH
sudo ansible-playbook -i inventory.yaml debug_network.yaml 
popd

phase "Look at Artifacts"
pushd . 
cd $CREATE_GRAPH
ls -ltr artifacts/*png
popd

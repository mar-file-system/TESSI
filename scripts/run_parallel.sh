#!/bin/bash 

# Define phases and their directories
declare -A phases
phases[gold_vms]="make_golds"
phases[network]="wireguard"
phases[vms]="opentofu/dynamic_hosts_libvirt_vms"
phases[artifacts]="network_graph"

# Define cleanup and create commands for each phase
declare -A commands
commands[gold_vms_clean]="ansible-playbook -i inventory.yaml make_golds.yaml --tags makeclean"
commands[gold_vms_create]="ansible-playbook -i inventory.yaml make_golds.yaml"

commands[network_clean]="ansible-playbook -i inventory.yaml create_wireguard_tunnels.yaml --tags makeclean"
commands[network_create]="ansible-playbook -i inventory.yaml create_wireguard_tunnels.yaml"

commands[vms_clean]="tofu destroy --auto-approve"
commands[vms_create]="cp /tmp/system_description.tf . && tofu apply --auto-approve"

commands[artifacts_clean]="\rm -f artifacts/*png"
commands[artifacts_create]="ansible-playbook -i inventory.yaml make_network_graph.yaml && ansible-playbook -i inventory.yaml debug_network.yaml && ls -ltr artifacts/*png"

# Define the ordered list of phases
phase_order=("gold_vms" "network" "vms" "artifacts")

# Define a function for phase messages
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

# Function to process a phase
process_phase() {
  local phase_name="$1"
  local action="$2" # clean or create
  local command_key="${phase_name}_${action}"
  local dry_run=0 # Set to 1 for dry-run, 0 for execution

  if [[ -n "${commands[$command_key]}" ]]; then
    pushd . > /dev/null
    cd "${phases[$phase_name]}"
    phase "${action^} $phase_name"
    if [[ $dry_run -eq 1 ]]; then
      echo "[Dry Run] cd ${phases[$phase_name]} && ${commands[$command_key]}"
    else
      sudo bash -c "${commands[$command_key]}"
    fi
    popd > /dev/null
  fi
}

# Execute all cleanup phases in reverse order
for (( idx=${#phase_order[@]}-1 ; idx>=0 ; idx-- )); do
  process_phase "${phase_order[idx]}" "clean"
done

# Execute all creation phases
for phase_name in "${phase_order[@]}"; do
  process_phase "$phase_name" "create"
done

echo "All done!"


#!/bin/bash

commands=(
  "./install_dependencies.sh"
  "./start_services.sh"
  "./create_physical_bridge.sh"
  "./create_virtual_bridge.sh"
)

for cmd in "${commands[@]}"; do
  echo "Running: $cmd"
  eval $cmd
  if [ $? -ne 0 ]; then
    echo "Command failed: $cmd"
    exit 1
  fi
done


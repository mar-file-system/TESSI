#!/bin/bash

# Source the variables file
source ./variables.sh

# Array of services to start (only libvirtd needed now)
SERVICES=(
  "libvirtd"
)

# Start and enable each service
for service in "${SERVICES[@]}"; do
  echo "Starting $service..."
  sudo systemctl start "$service"
  
  echo "Enabling $service to start on boot..."
  sudo systemctl enable "$service"
  
  # Check the status to confirm the service is running
  sudo systemctl status "$service" --no-pager
done

echo "libvirt service started and enabled to run at boot."


# Wait for the VMs to be assigned IP addresses
data "external" "vm_ips" {
  for_each = { for vm in var.vm_name : vm.name => vm }

  depends_on = [
    module.vms
  ]

  program = ["bash", "-c", <<EOT
    for i in {1..10}; do
      ips=$(ssh root@${each.value.host} virsh domifaddr ${each.key} | grep ipv4 | awk '{print $4}' | cut -d'/' -f1 | tr '\\n' ',' | sed 's/,$//')
      if [ -n "$ips" ]; then
        echo "{\"output\": \"$(echo $ips | sed 's/\"/\\\\\"/g')\"}"
        exit 0
      fi
      sleep 60  # Wait before retrying
    done
    echo '{"output": ""}'  # Return an empty string if no IPs found after retries
  EOT
  ]
}

# Output the IP addresses for all VMs
output "vm_ips" {
  value = { for vm in var.vm_name : vm.name => split(",", data.external.vm_ips[vm.name].result["output"]) }
}


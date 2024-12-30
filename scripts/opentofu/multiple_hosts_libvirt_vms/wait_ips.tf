
# wait for the VMs to be assigned IP addressess
data "external" "vm_ips" {
  for_each = { for vm in var.vm_name : vm.name => vm }

  depends_on = [
    module.in07_vms,
    module.in16_vms
  ]

  program = ["bash", "-c", <<EOT
    for i in {1..10}; do
      ip=$(ssh root@${each.value.host} virsh domifaddr ${each.key} | grep -m1 ipv4 | awk '{print $4}' | cut -d'/' -f1)
      if [ -n "$ip" ]; then
        echo "{\"output\": \"$ip\"}"
        exit 0
      fi
      sleep 60  # Wait before retrying
    done
    echo '{"output": ""}'  # Return an empty string if no IP found after retries
  EOT
  ]
}


# Output the IP addresses for all VMs
output "vm_ips" {
  value = { for vm in var.vm_name : vm.name => data.external.vm_ips[vm.name].result["output"] }
}

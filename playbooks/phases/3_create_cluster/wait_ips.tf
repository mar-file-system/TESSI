# Wait for the VMs to be assigned IP addresses
data "external" "vm_ips" {
  for_each = { for vm in var.vm_name : vm.name => vm }

  depends_on = [
    module.vms
  ]

  program = ["bash", "-c", <<EOT
  for i in {1..10}; do
    ok=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
         root@${each.value.host} "nc -z -w3 ${each.key} 22 && echo ok" 2>/dev/null)
    if [ "$ok" = "ok" ]; then
      echo '{"output": "up"}'
      exit 0
    fi
    sleep 60
  done

  echo '{"output": "error: unable to ssh into VM after 10 attempts"}'
  EOT
  ]
}

# Output the IP addresses for all VMs
output "vm_ips" {
  value = { for vm in var.vm_name : vm.name => split(",", data.external.vm_ips[vm.name].result["output"]) }
}


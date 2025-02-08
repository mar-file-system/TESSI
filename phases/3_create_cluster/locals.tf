locals {
  physicalhosts = {
    for host in distinct([for vm in var.vm_name : vm.host]) :
    host => "qemu+ssh://root@${host}/system"
  }

  # Generate a mapping of hosts to their VMs
  host_vms = {
    for host in distinct([for vm in var.vm_name : vm.host]) :
    host => tolist([for vm in var.vm_name : vm.name if vm.host == host])
  }
}

output "physicalhosts" {
  value = local.physicalhosts
}

# Output for VMs grouped by host
output "host_vms" {
  value = local.host_vms
}


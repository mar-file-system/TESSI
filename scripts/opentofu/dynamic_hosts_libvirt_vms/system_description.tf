variable "vm_name" {
  type = list(object({ 
    name             = string
    machine          = optional(string, "pc-q35-rhel8.2.0")
    memory           = optional(string, "2048")
    vcpu             = optional(number, 2)
    second_disk_size = optional(number, null)
    host             = string  # The short-hand for the host (e.g., "in07" or "in16")
    source_image     = optional(string, "/var/lib/libvirt/images/gold-beegfs-almalinux8-server.qcow2")  # Optional source image with default
    storage_pool     = optional(string, "default")
    netone           = optional(string, "default")
    nettwo           = optional(string, "wireguard-virt")
    #network          = optional(string, "vm-net")
  }))
  default = [
    {
      name            = "beegfs-client00"
      host            = "in07"
    },
    {
      name            = "beegfs-client01"
      host            = "in07"
    },
    {
      name            = "beegfs-meta00"
      second_disk_size = 5
      host            = "in07"
    },
    {
      name            = "beegfs-meta01"
      second_disk_size = 5
      host            = "in16"
    },
    {
      name            = "beegfs-data00"
      second_disk_size = 10
      host            = "in16"
    },
    {
      name            = "beegfs-data01"
      second_disk_size = 10
      host            = "in16"
    }
  ]
}

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

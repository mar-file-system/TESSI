terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
    }
  }
}

# Define hosts with their URIs
variable "hosts" {
  description = "Map of hosts and their libvirt URIs"
  type        = map(string)
  default     = {
    in07 = "qemu+ssh://root@in07/system"
    in16 = "qemu+ssh://root@in16/system"
  }
}

# Dynamic provider setup for libvirt
provider "libvirt" {
  alias    = "by_host"
  for_each = var.hosts

  uri = each.value
}

# redeclare the hosts into a new variable to suppress a warning about iterating over the same hosts 
locals {
  active_hosts = var.hosts
}

# Create a volume named "test_volume" on each active host
resource "libvirt_volume" "test_volume" {
  for_each = local.active_hosts

  name   = "test_volume"
  pool   = "default"         # Adjust pool name if needed
  size   = 1024 * 1024 * 10  # 10 MB volume
  format = "qcow2"

  provider = libvirt.by_host[each.key]
}

# Output the created volumes
output "volume_paths" {
  description = "Paths to the created volumes"
  value = { for host, vol in libvirt_volume.test_volume : host => vol.id }
}


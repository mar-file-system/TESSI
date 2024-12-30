terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
    }
  }
} 
  
# Providers
provider "libvirt" {
  alias = "in07"
  uri   = "qemu+ssh://root@in07/system"
} 
  
provider "libvirt" {
  alias = "in16"
  uri   = "qemu+ssh://root@in16/system"
}   

locals {
  primary_volumes_in07   = { for name, mod in module.in07_volumes : name => mod.volume_id }
  secondary_volumes_in07 = { for name, mod in module.in07_second_volumes : name => mod.volume_id }

  primary_volumes_in16   = { for name, mod in module.in16_volumes : name => mod.volume_id }
  secondary_volumes_in16 = { for name, mod in module.in16_second_volumes : name => mod.volume_id }
}

output "primary_volumes_in07" {
  value = local.primary_volumes_in07
}

output "secondary_volumes_in07" {
  value = local.secondary_volumes_in07
}

output "primary_volumes_in16" {
  value = local.primary_volumes_in16
}

output "secondary_volumes_in16" {
  value = local.secondary_volumes_in16
}

output "in07_vms" {
  description = "Details of the VMs created on in07"
  value = { for name, mod in module.in07_vms : name => mod }
}

output "in16_vms" {
  description = "Details of the VMs created on in16"
  value = { for name, mod in module.in16_vms : name => mod }
}



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
  primary_volumes   = { for name, mod in module.in07_volumes : name => mod.volume_id }
  secondary_volumes = { for name, mod in module.in07_second_volumes : name => mod.volume_id }
}

output "primary_volumes" {
  value = local.primary_volumes
}

output "secondary_volumes" {
  value = local.secondary_volumes
}

# define the VMs here 
module "in07_vms" {
  source = "./modules/libvirt_vm"

  for_each = { for vm in var.vm_name : vm.name => vm if vm.host == "in07" }

  name        = each.value.name 
  memory      = each.value.memory
  vcpu        = each.value.vcpu     
  machine     = each.value.machine
  primary    = local.primary_volumes[each.key]
  secondary  = try(local.secondary_volumes[each.key], null)
  network     = each.value.network
  
  providers = {
    libvirt = libvirt.in07
  }

  depends_on = [module.in07_volumes, module.in07_second_volumes]

}

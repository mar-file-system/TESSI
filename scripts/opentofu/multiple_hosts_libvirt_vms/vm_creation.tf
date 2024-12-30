# define the VMs here 
module "in07_vms" {
  source = "./modules/libvirt_vm"

  for_each = { for vm in var.vm_name : vm.name => vm if vm.host == "in07" }

  name        = each.value.name 
  memory      = each.value.memory
  vcpu        = each.value.vcpu     
  machine     = each.value.machine
  primary    = local.primary_volumes_in07[each.key]
  secondary  = try(local.secondary_volumes_in07[each.key], null)
  netone      = each.value.netone
  nettwo      = each.value.nettwo
  
  providers = {
    libvirt = libvirt.in07
  }

  depends_on = [module.in07_volumes, module.in07_second_volumes]

}

module "in16_vms" {
  source = "./modules/libvirt_vm"

  for_each = { for vm in var.vm_name : vm.name => vm if vm.host == "in16" }

  name        = each.value.name
  memory      = each.value.memory
  vcpu        = each.value.vcpu
  machine     = each.value.machine
  primary     = local.primary_volumes_in16[each.key]
  secondary   = try(local.secondary_volumes_in16[each.key], null)
  netone      = each.value.netone
  nettwo      = each.value.nettwo

  providers = {
    libvirt = libvirt.in16
  }

  depends_on = [module.in16_volumes, module.in16_second_volumes]
}

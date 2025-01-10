module "vms" {
  source = "./modules/libvirt_vm"

  for_each = { for vm in var.vm_name : vm.name => vm }

  name        = each.value.name 
  memory      = each.value.memory
  vcpu        = each.value.vcpu     
  machine     = each.value.machine
  primary     = module.volumes["${each.key}-primary"].volume_id
  secondary   = try(module.volumes["${each.key}-secondary"].volume_id, null)
  netone      = each.value.netone
  nettwo      = each.value.nettwo
  mac_address = each.value.mac_address
  
  providers = {
    libvirt = libvirt.by_host[each.value.host]
  }
}


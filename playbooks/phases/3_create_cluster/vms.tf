module "vms" {
  source = "./modules/libvirt_vm"
  
  for_each = { for vm in var.vm_name : vm.name => vm }
  
  name        = each.value.name
  memory      = each.value.memory
  vcpu        = each.value.vcpu
  machine     = each.value.machine 
  primary     = module.volumes["${each.key}-primary"].volume_id
  extra_disks = (
    length(each.value.extra_hdds) > 0 ? 
    [for idx, disk in each.value.extra_hdds : module.volumes["${each.key}-${idx}"].volume_id] 
    : []
  )
  cloud_vol   = try(module.volumes["${each.key}-cloudinit"].volume_id, null)
  netone      = each.value.netone
  nettwo      = each.value.nettwo
  mac_address = each.value.mac_address
  
  depends_on = [ 
    module.volumes
  ]
  
  providers = {
    libvirt = libvirt.by_host[each.value.host]
  }
}

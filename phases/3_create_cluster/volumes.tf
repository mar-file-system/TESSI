locals {
  primary_and_secondary = merge(
    { for vm in var.vm_name : "${vm.name}-primary" => merge(vm, { pool_key = "${vm.storage_pool}-${vm.host}" }) },
    { for vm in var.vm_name : "${vm.name}-secondary" => merge(vm, { pool_key = "${vm.storage_pool}-${vm.host}" }) if vm.second_disk_size != null }
  )

  ci_volumes = {
    for vm in var.vm_name : "${vm.name}-cloudinit" => merge(vm, { pool_key = "${vm.storage_pool}-${vm.host}" })
    if vm.cloudinit != null
  }

  all_volumes = merge(local.primary_and_secondary, local.ci_volumes)
}
  
module "volumes" {    
  source   = "./modules/libvirt_volume"
  for_each = local.all_volumes
  
  name       = each.key 
  pool       = each.value.storage_pool
  
  providers = {
    libvirt = libvirt.by_host[each.value.host]
  }

  // For primary disks: use a source image (qcow2); for secondary disks: use size (raw);
  // for cloudinit disks: pass the cloudinit user_data.
  source_img = strcontains(each.key, "primary") ? each.value.source_image : null
  size       = strcontains(each.key, "secondary") ? each.value.second_disk_size * 1024 * 1024 * 1024 : null
  format     = strcontains(each.key, "primary") ? "qcow2" : "raw"
  cloudinit_user_data = strcontains(each.key, "cloudinit") ? each.value.cloudinit : null

  depends_on = [
    module.pools,
  ]
}

output "volume_paths" {
  description = "Paths to all created volumes, including primary, secondary, and cloudinit"
  value       = { for key, instance in module.volumes : key => instance.volume_id }
}

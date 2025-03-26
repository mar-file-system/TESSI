locals {
  primary_disks = {
    for vm in var.vm_name : "${vm.name}-primary" => merge(vm, { pool_key = "${vm.storage_pool}-${vm.host}" })
  }

  # Properly handling extra_disks
  extra_disks = {
    for vm in var.vm_name : 
    "${vm.name}" => {
      for idx, disk in vm.extra_hdds : 
      "${vm.name}-${idx}" => {
        pool_key     = "${vm.storage_pool}-${vm.host}"
        disk_size    = disk.size
        storage_pool = vm.storage_pool
        host         = vm.host
      }
    } 
  } 
  # Remove empty objects from extra_disks so they don’t interfere
  extra_disks_flat = merge(flatten([for v in values(local.extra_disks) : v])...)

  ci_volumes = {
    for vm in var.vm_name : "${vm.name}-cloudinit" => merge(vm, {
      pool_key            = "${vm.storage_pool}-${vm.host}"
      cloudinit_user_data = vm.cloudinit_user_data
      cloudinit_network   = vm.cloudinit_network  
    })
    if vm.cloudinit_user_data != null
  }

  # Merge everything properly
  all_volumes = merge(local.primary_disks, local.extra_disks_flat, local.ci_volumes)
}

module "volumes" {
  source   = "./modules/libvirt_volume"
  for_each = local.all_volumes

  name       = each.key
  pool       = each.value.storage_pool

  providers = {
    libvirt = libvirt.by_host[each.value.host]
  }

  # Primary disks use the source image (qcow2)
  source_img = strcontains(each.key, "primary") ? each.value.source_image : null
  
  # Extra disks must have a size, primary disks do not
  size       = strcontains(each.key, "primary") ? null : lookup(each.value, "disk_size", 0) 

  format     = strcontains(each.key, "primary") ? "qcow2" : "raw"
  cloudinit_user_data = strcontains(each.key, "cloudinit") ? each.value.cloudinit_user_data : null
  cloudinit_network   = strcontains(each.key, "cloudinit") ? each.value.cloudinit_network   : null

  depends_on = [module.pools]
}


output "volume_paths" {
  description = "Paths to all created volumes, including primary, extra, and cloudinit"
  value       = { for key, instance in module.volumes : key => instance.volume_id }
}

output "debug_disk_sizes" {
  value = { for key, instance in local.all_volumes : key => lookup(instance, "disk_size", "MISSING") }
}

output "debug_final_disk_sizes" {
  value = { for key, instance in local.extra_disks_flat : key => instance.disk_size }
}


# Regular volumes module
module "volumes" {
  source = "./modules/libvirt_volume"

  for_each = merge(
    { for vm in var.vm_name : "${vm.name}-primary" => vm },
    { for vm in var.vm_name : "${vm.name}-secondary" => vm if vm.second_disk_size != null }
  )

  name        = each.key
  pool        = each.value.storage_pool
  source_img  = strcontains(each.key, "primary") ? each.value.source_image : null
  size        = strcontains(each.key, "secondary") ? each.value.second_disk_size * 1024 * 1024 * 1024 : null
  format      = strcontains(each.key, "primary") ? "qcow2" : "raw"

  providers = {
    libvirt = libvirt.by_host[each.value.host]
  }
}

# Outputs
output "volume_paths" {
  description = "Paths to all created volumes, including primary and secondary"
  value = { for key, instance in module.volumes : key => instance.volume_id }
}

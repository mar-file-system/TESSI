locals {
  unique_pools = distinct([
    for vm in var.vm_name : {
      name               = vm.storage_pool,
      host               = vm.host
      storage_pool_path  = vm.storage_pool_path
    }
  ])

  unique_pools_map = {
    for pool in local.unique_pools :
    "${pool.name}-${pool.host}" => pool
  }
}

module "pools" {
  source = "./modules/libvirt_pool"

  for_each = local.unique_pools_map

  name = each.value.name
  pool_path = "${each.value.storage_pool_path}/${each.value.name}_pool"

  providers = {
    libvirt = libvirt.by_host[each.value.host]
  }
}

output "created_pools" {
  description = "A map of the created libvirt storage pools"
  value = {
    for key, pool in module.pools :
    key => {
      name  = pool.pool_name
      path  = pool.pool_path  
    }
  }
}

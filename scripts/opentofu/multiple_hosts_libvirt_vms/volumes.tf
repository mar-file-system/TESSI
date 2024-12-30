# define the primary volumes here
module "in07_volumes" {
  source = "./modules/libvirt_volume"

  for_each = { for vm in var.vm_name : vm.name => vm if vm.host == "in07" }

  name        = "${each.value.name}.volume"
  pool        = each.value.storage_pool
  source_img  = each.value.source_image
  size        = null
  format      = "qcow2"

  providers = {
    libvirt = libvirt.in07
  }
}

module "in16_volumes" {
  source = "./modules/libvirt_volume"

  for_each = { for vm in var.vm_name : vm.name => vm if vm.host == "in16" }

  name        = "${each.value.name}.volume"
  pool        = each.value.storage_pool
  source_img  = each.value.source_image
  size        = null
  format      = "qcow2"

  providers = {
    libvirt = libvirt.in16
  }
}

# Convert GB to bytes (GB * 1024^3 = bytes)
locals {
  gb_to_bytes = 1024 * 1024 * 1024
}

# define the secondary volumes here
module "in07_second_volumes" {
  source = "./modules/libvirt_volume"

  for_each   = { for vm in var.vm_name : vm.name => vm if vm.second_disk_size != null && vm.host == "in07"}
  name       = "${each.value.name}.second"
  pool       = each.value.storage_pool
  source_img = null
  size       = each.value.second_disk_size * local.gb_to_bytes  # Convert second disk size from GB to bytes
  format     = "raw"                                            # Raw format for second disk

  providers = {
    libvirt = libvirt.in07
  }
}

module "in16_second_volumes" {
  source = "./modules/libvirt_volume"

  for_each   = { for vm in var.vm_name : vm.name => vm if vm.second_disk_size != null && vm.host == "in16"}
  name       = "${each.value.name}.second"
  pool       = each.value.storage_pool
  source_img = null
  size       = each.value.second_disk_size * local.gb_to_bytes  # Convert second disk size from GB to bytes
  format     = "raw"                                            # Raw format for second disk

  providers = {
    libvirt = libvirt.in16
  }
}




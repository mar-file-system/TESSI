# Convert GB to bytes (GB * 1024^3 = bytes)
locals {
  gb_to_bytes = 1024 * 1024 * 1024
}

# Primary disk creation from a customizable qcow2 image for in07
resource "libvirt_volume" "in07_volumes" {
  provider = libvirt.in07
  for_each = { for vm in var.vm_name : vm.name => vm if vm.host == "in07"}
  name     = "${each.value.name}-primary"
  pool     = each.value.storage_pool
  source   = each.value.source_image                   # Use the VM-specific or default qcow2 image
  format   = "qcow2"
}

# Primary disk creation from a customizable qcow2 image for in16
resource "libvirt_volume" "in16_volumes" {
  provider = libvirt.in16
  for_each = { for vm in var.vm_name : vm.name => vm if vm.host == "in16"}
  name     = "${each.value.name}-primary"
  pool     = each.value.storage_pool
  source   = each.value.source_image                   # Use the VM-specific or default qcow2 image
  format   = "qcow2"
}

# Conditional second disk creation in raw format (no source image) for in07
resource "libvirt_volume" "in07_second_volumes" {
  provider = libvirt.in07
  for_each = { for vm in var.vm_name : vm.name => vm if vm.second_disk_size != null && vm.host == "in07"}
  name     = "${each.value.name}-secondary"
  pool     = "${each.value.storage_pool}"
  size     = each.value.second_disk_size * local.gb_to_bytes  # Convert second disk size from GB to bytes
  format   = "raw"                                            # Raw format for second disk
}

# Conditional second disk creation in raw format (no source image) for in16
resource "libvirt_volume" "in16_second_volumes" {
  provider = libvirt.in16
  for_each = { for vm in var.vm_name : vm.name => vm if vm.second_disk_size != null && vm.host == "in16"}
  name     = "${each.value.name}-secondary"
  pool     = "${each.value.storage_pool}"
  size     = each.value.second_disk_size * local.gb_to_bytes  # Convert second disk size from GB to bytes
  format   = "raw"                                            # Raw format for second disk
}


terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
    }
  }
}

variable "name" {}
variable "pool" {}
variable "source_img" {}
variable "size" {}
variable "format" {}
variable "cloudinit_user_data" {
  type    = string
  default = null
}

# Create a regular volume if no cloudinit_user_data is provided.
resource "libvirt_volume" "volume" {
  count  = var.cloudinit_user_data == null ? 1 : 0

  name   = var.name
  pool   = var.pool
  source = var.source_img
  size   = var.size
  format = var.format
}

# Create a cloud-init disk if cloudinit_user_data is provided.
resource "libvirt_cloudinit_disk" "cloudinit" {
  count     = var.cloudinit_user_data != null ? 1 : 0

  name      = var.name
  pool      = var.pool
  user_data = var.cloudinit_user_data
}

output "volume_id" {
  value = var.cloudinit_user_data == null ? libvirt_volume.volume[0].id : libvirt_cloudinit_disk.cloudinit[0].id
}

output "debug_source" {
  value = var.source_img
}

output "debug_size" {
  value = var.size
}

output "volume_path" {
  value = var.cloudinit_user_data == null ? libvirt_volume.volume[0].path : null
  description = "The path to the libvirt volume (if no cloud-init data is used)"
}

output "cloudinit_path" {
  value = var.cloudinit_user_data != null ? libvirt_cloudinit_disk.cloudinit[0].path : null
  description = "The path to the cloud-init disk (if cloud-init data is used)"
}

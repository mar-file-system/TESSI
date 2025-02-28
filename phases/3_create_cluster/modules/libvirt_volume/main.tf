terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
    }
  }
}

variable "name" {}
variable "pool" {}
variable "source_img" {
  type    = string
  default = null  # Optional, only used for primary disks
}
variable "size" {
  type    = number
  default = null  # Optional, only used for extra disks
}
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
  source = var.source_img != null ? var.source_img : null  # Use source image only if provided
  size   = var.source_img == null ? var.size * 1024 * 1024 * 1024 : null  # Use size only for extra disks
  format = var.format
}

# Create a cloud-init disk if cloudinit_user_data is provided.
resource "libvirt_cloudinit_disk" "cloudinit" {
  count     = var.cloudinit_user_data != null ? 1 : 0

  name      = var.name
  pool      = var.pool
  user_data = var.cloudinit_user_data
}

# Output the correct volume ID (either cloud-init or standard volume)
output "volume_id" {
  value = var.cloudinit_user_data == null ? libvirt_volume.volume[0].id : libvirt_cloudinit_disk.cloudinit[0].id
}

# Debug Outputs
output "debug_source" {
  value = var.source_img
}

output "debug_size" {
  value = var.size
}

output "debug_volume_size" {
  value = var.source_img == null ? var.size : "USED_SOURCE_IMG"
}

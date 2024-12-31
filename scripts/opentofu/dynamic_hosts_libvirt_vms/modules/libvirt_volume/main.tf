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

resource "libvirt_volume" "volume" {
  name     = var.name 
  pool     = var.pool
  source   = var.source_img
  size     = var.size
  format   = var.format 
}

output "volume_id" {
  value = libvirt_volume.volume.id
}


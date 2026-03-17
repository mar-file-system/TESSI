terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
    }
  } 
} 

variable "name" {}
variable "pool_path" {}

resource "libvirt_pool" "pool" {
  name = var.name
  type = "dir"
  path = var.pool_path
}

output "pool_name" {
  value = libvirt_pool.pool.name
}

output "pool_path" {
  description = "The path where the storage pool is created"
  value       = var.pool_path 
}

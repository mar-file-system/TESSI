terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
    }
  }
}

variable "name" {}
variable "memory" {}
variable "vcpu" {}
variable "machine" {}
variable "primary" {}
variable "secondary" {}
variable "netone" {}
variable "nettwo" {}

resource "libvirt_domain" "domain" {
  name       = var.name 
  memory     = var.memory 
  vcpu       = var.vcpu 
  machine    = var.machine

  running    = true
  autostart  = true

  # Attach primary disk
  disk {
    volume_id = var.primary 
  }

  # Attach secondary disk if it exists
  dynamic "disk" {
    for_each = var.secondary != null ? [1] : []
    content {
      volume_id = var.secondary
    }
  }

  # primary default network
  network_interface {
    network_name = var.netone
  }

  # secondary storage network
  network_interface {
    network_name = var.nettwo 
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

  depends_on = [
    var.primary,
    var.secondary
  ]

}

output "vm_id" {
  value = libvirt_domain.domain.id
}

output "vm_name" {
  value = libvirt_domain.domain.name
}

output "vm_state" {
  value = libvirt_domain.domain.running
}

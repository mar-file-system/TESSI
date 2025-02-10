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
variable "primary" {}         // Primary disk volume ID
variable "secondary" {}       // Secondary disk volume ID (optional)
variable "netone" {}
variable "nettwo" {}
variable "mac_address" {}
variable "cloud_vol" {      // New variable to receive the cloud‑init volume (if any)
  type    = string
  default = null
}

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
  
  # Attach the cloud-init disk if provided
  cloudinit = var.cloud_vol
  
  # Adjust XML to work around Q35 IDE issues
  xml {
    xslt = file("${path.module}/nodes-adjust.xslt")
  }

  boot_device {
    dev = ["cdrom", "hd"]
  }

  # Primary network interface
  network_interface {
    network_name = var.netone
  }

  # Secondary network interface
  network_interface {
    network_name = var.nettwo
    mac          = var.mac_address
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }
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


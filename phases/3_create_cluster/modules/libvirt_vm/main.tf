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
variable "primary" {}       # Primary disk volume ID
variable "extra_disks" {    # List of extra disk volume IDs
  type    = list(string)
  default = []
}
variable "netone" {}
variable "nettwo" {}
variable "mac_address" {}
variable "cloud_vol" {      # Cloud-init volume (if any)
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

  # Attach extra disks dynamically
  dynamic "disk" {
    for_each = var.extra_disks
    content {
      volume_id = disk.value
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


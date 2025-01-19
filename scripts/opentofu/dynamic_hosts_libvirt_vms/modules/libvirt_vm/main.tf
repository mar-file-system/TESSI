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
variable "mac_address" {}
variable "cloudinit_user_data" {}

resource "libvirt_cloudinit_disk" "cloudinit" {
  name      = "${var.name}-cloudinit.iso"
  user_data = var.cloudinit_user_data
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

  # Attach cloudinit disk the proper way which fails because q35 machine doesn't support ide
  cloudinit = libvirt_cloudinit_disk.cloudinit.id

  # weird thing. need to transform the XML. Refer to:
  # https://gist.github.com/dariush/7405cbf62835e03d0b5c953d798a87cd and
  # https://github.com/dmacvicar/terraform-provider-libvirt/issues/667
  xml {
    xslt = file("${path.module}/nodes-adjust.xslt")
  }

  boot_device {
    dev = ["cdrom", "hd"]
  }

  # primary default network
  network_interface {
    network_name = var.netone
  }

  # secondary storage network
  network_interface {
    network_name = var.nettwo 
    mac          = var.mac_address
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

  depends_on = [
    var.primary,
    var.secondary,
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

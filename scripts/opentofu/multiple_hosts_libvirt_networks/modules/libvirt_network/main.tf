terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
    }
  }
}

variable "name" {}
variable "bridge_name" {}
variable "addresses" {
  description = "List of network addresses in CIDR notation"
  type        = list(string)
}

resource "libvirt_network" "network" {
  name   = var.name
  bridge = var.bridge_name

  mode = "nat"

  addresses = var.addresses

  domain = var.name

  dns {
    enabled = true
    local_only = false

     hosts  {
         hostname = "googledns1"
         ip = "8.8.8.8"
       }
     hosts {
         hostname = "googledns2"
         ip = "8.8.4.4"
       }
     
  }

  dhcp {
    enabled = true
  }
}


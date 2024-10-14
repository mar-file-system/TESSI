variable "network_name" {
  type    = string
  default = "vm-net"
}

variable "network_cidr" {
  type    = string
  default = "192.168.100.0/24"
}

variable "bridge_interface" {
  type    = string
  default = "br0"
}

# Network on in07
resource "libvirt_network" "in07_bridge" {
  name      = var.network_name
  mode      = "bridge"
  bridge    = var.bridge_interface
  autostart = true
  addresses = [var.network_cidr]

  provider = libvirt.in07
}

# Network on in16
resource "libvirt_network" "in16_bridge" {
  name      = var.network_name
  mode      = "bridge"
  bridge    = var.bridge_interface
  autostart = true
  addresses = [var.network_cidr]

  provider = libvirt.in16
}

terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
    }
  }
} 
  
# Providers
provider "libvirt" {
  alias = "in07"
  uri   = "qemu+ssh://root@in07/system"
} 
  
provider "libvirt" {
  alias = "in16"
  uri   = "qemu+ssh://root@in16/system"
}   

# Base address for the networks
variable "base_address" {
  default = "192.168.57"
}

# Network for in07
module "in07_network" {
  source = "./modules/libvirt_network"
       
  name        = "libvirt-hostonly"
  bridge_name = "libvirtbr1"
  addresses   = ["${var.base_address}.0/27"]
       
  providers = {
    libvirt = libvirt.in07
  }
} 

# Network for in16
module "in16_network" {
  source = "./modules/libvirt_network"

  name        = "libvirt-hostonly"
  bridge_name = "libvirtbr1"
  addresses   = ["${var.base_address}.32/27"]
  
  providers = { 
    libvirt = libvirt.in16
  }
} 


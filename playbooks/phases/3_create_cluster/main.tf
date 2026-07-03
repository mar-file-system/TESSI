terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
      version = "~> 0.7.0"
    }
  }
}

# Dynamic provider setup for libvirt
provider "libvirt" {
  alias    = "by_host"
  for_each = local.physicalhosts

  uri = each.value
}

# redeclare the hosts into a new variable to suppress a warning about iterating over the same hosts 
locals {
  hosts = local.physicalhosts
}


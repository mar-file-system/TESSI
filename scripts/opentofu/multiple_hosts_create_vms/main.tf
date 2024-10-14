terraform {
 required_version = ">= 0.13"
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      #version = "0.6.14" # this works
      #version = "0.8.0"  # this crashes
      #version = "0.7.6"   # this works
      # refer to ../minimal_broken/README for instructions to fix with 0.8.0
    }
  }
}

provider "libvirt" {
  uri = "qemu:///system"
}

provider "libvirt" {
  alias = "in07"
  uri   = "qemu+ssh://root@in07/system"
}

provider "libvirt" {
  alias = "in16"
  uri   = "qemu+ssh://root@in16/system"
}

resource "libvirt_volume" "in07-qcow2" {
  provider = libvirt.in07
  name   = "in07-qcow2"
  pool   = "default"
  format = "qcow2"
  size   = 100000
}

resource "libvirt_volume" "in16-qcow2" {
  provider = libvirt.in16
  name     = "in16-qcow2"
  pool     = "default"
  format   = "qcow2"
  size     = 100000
}

resource "libvirt_domain" "in07-domain" {
  provider = libvirt.in07
  name     = "in07vm01"
  memory   = "2048"
  vcpu     = 2

  disk {
    volume_id = libvirt_volume.in07-qcow2.id
  }

  depends_on = [libvirt_volume.in07-qcow2]
}

resource "libvirt_domain" "in16-domain" {
  provider = libvirt.in16
  name     = "in16vm01"
  memory   = "2048"
  vcpu     = 2

  disk {
    volume_id = libvirt_volume.in16-qcow2.id
  }

  depends_on = [libvirt_volume.in16-qcow2]
}


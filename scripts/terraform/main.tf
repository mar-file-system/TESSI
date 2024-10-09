terraform {
  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
    }
  }
}

provider "libvirt" {
  uri = "qemu:///system"
}

# Create a new storage pool in a unique directory
resource "libvirt_pool" "terraform_storage_pool" {
  name = "terraform_new_pool"
  type = "dir"
  path = "/var/lib/libvirt/terraform_images"  # Specify a new path for the pool
}

# Create a volume in the new storage pool
resource "libvirt_volume" "terraform_boot_hdd" {
  name   = "terraform_boot_hdd.qcow2"
  pool   = libvirt_pool.terraform_storage_pool.name
  size   = 12         # Size in GB
  format = "qcow2"
}

resource "libvirt_cloudinit_disk" "commoninit" {
  name      = "commoninit.iso"
  pool      = libvirt_pool.terraform_storage_pool.name
  user_data = <<-EOT
    #cloud-config
    password: password
    chpasswd: { expire: False }
    ssh_authorized_keys:
      - $(cat /home/jbent/.ssh/authorized_keys)
  EOT
}

resource "libvirt_domain" "bootstrap_vm" {
  name   = "bootstrap_vm"
  memory = 4096       # Memory in MB
  vcpu   = 2

  # Attach the boot volume (HDD)
  disk {
    volume_id = libvirt_volume.terraform_boot_hdd.id
  }

  # Attach the CD-ROM with the installation media
  disk {
    file = "/mnt/usrc-storage-nfs/jbent/images/alma/AlmaLinux-8.10-x86_64-minimal.iso"
  }

  # Attach the Cloud-init ISO by explicitly providing the file path
  disk {
    file = "/var/lib/libvirt/terraform_images/commoninit.iso"
  }

  # Network interface
  network_interface {
    network_name = "default"
  }

  # Console setup (you need to specify a target port)
  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

  # Graphics (optional)
  graphics {
    type = "vnc"
    listen_type = "none"
  }

  # Boot configuration
  boot_device {
    dev = ["cdrom", "hd"]
  }
}


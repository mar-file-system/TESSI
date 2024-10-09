# from https://www.youtube.com/watch?v=Lt8cHwy-jEM
# from https://low-orbit.net/terraform-kvm
# note the comment on the youtube which explains that the qcow2 image was previously created
# I modified to use the gold image which I created by:
# sudo virsh domblklist gold-beegfs-almalinux8-server # to find the path
# qemu-img convert -O qcow2 <path> <new_path.qcow2>

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

locals {
    host_list = toset([ "host1", "host2", "host3" ])
}

resource "libvirt_volume" "volumes" {
    for_each = local.host_list
        name = "${each.key}.qcow2"
        pool = "default"
        source = "/var/lib/libvirt/images/gold-beegfs-almalinux8-server.qcow2"
        format = "qcow2"
}

resource "libvirt_domain" "hosts" {
    for_each = local.host_list
        name   = each.key
        memory = "2048"
        vcpu   = 2

        network_interface {
            network_name = "hostonly-net"
        }

        disk {
            volume_id = libvirt_volume.volumes[each.key].id
       }

        console {
            type = "pty"
            target_type = "serial"
            target_port = "0"
        }

        graphics {
            type = "vnc"
            listen_type = "address"
            listen_address = "0.0.0.0"
            autoport = true
        }
}


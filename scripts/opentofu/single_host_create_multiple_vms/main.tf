# from https://www.youtube.com/watch?v=Lt8cHwy-jEM
# from https://low-orbit.net/terraform-kvm
# note the comment on the youtube which explains that the qcow2 image was previously created
# I modified to use the gold image which I created by:
# sudo virsh domblklist gold-beegfs-almalinux8-server # to find the path
# qemu-img convert -O qcow2 <path> <new_path.qcow2>
# also from https://www.reddit.com/r/Terraform/comments/vf7c62/comment/icxfagp/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button

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

variable "vm_name" {
  type = list(object({
    number          = string
    name            = string
    machine         = optional(string, "pc-q35-rhel8.2.0") # the machine type used in the source image so make sure it matches
    memory          = optional(string, "2048")  # Default memory
    vcpu            = optional(number, 2)       # Default vCPU
    second_disk_size = optional(number, null)   # Optional: Second disk size in GB (null by default)
    source_image    = optional(string, "/var/lib/libvirt/images/gold-beegfs-almalinux8-server.qcow2")  # Optional source image with default
  }))
  default = [
    {
      number          = "01"
      name            = "athreos"
      second_disk_size = 10                     # 10GB secondary disk (raw format)
    },
    {
      number          = "02"
      name            = "kratos"
      memory          = "4096"                  # Custom memory
      vcpu            = 4                       # Custom vCPU
    },
    {
      number          = "03"
      name            = "freya"
      second_disk_size = 5                      # 5GB secondary disk (raw format)
    }
  ]
}

# Convert GB to bytes (GB * 1024^3 = bytes)
locals {
  gb_to_bytes = 1024 * 1024 * 1024
}

# Primary disk creation from a customizable qcow2 image
resource "libvirt_volume" "volumes" {
  for_each = { for vm in var.vm_name : vm.name => vm }
  name     = "${each.value.number}-playground-${each.value.name}-primary"
  pool     = "default"
  source   = each.value.source_image                   # Use the VM-specific or default qcow2 image
  format   = "qcow2"
}

# Conditional second disk creation in raw format (no source image)
resource "libvirt_volume" "second_volumes" {
  for_each = { for vm in var.vm_name : vm.name => vm if vm.second_disk_size != null }
  name     = "${each.value.number}-playground-${each.value.name}-secondary"
  pool     = "default"
  size     = each.value.second_disk_size * local.gb_to_bytes  # Convert second disk size from GB to bytes
  format   = "raw"                                            # Raw format for second disk
}

resource "libvirt_domain" "vms" {
  for_each   = { for vm in var.vm_name : vm.name => vm }
  #name       = "${each.value.number}-playground-${each.value.name}"
  name       = "${each.value.name}"
  memory     = each.value.memory  # Default memory if not specified
  vcpu       = each.value.vcpu    # Default vCPU if not specified
  running    = true
  autostart  = true
  machine    = each.value.machine

  # Attach primary disk
  disk {
    volume_id = libvirt_volume.volumes[each.key].id
  }

  # Attach secondary disk if it exists
  dynamic "disk" {
    for_each = (each.value.second_disk_size != null) ? [1] : []
    content {
      volume_id = libvirt_volume.second_volumes[each.key].id
    }
  }

  # Network interface (you can adjust as needed)
  network_interface {
    network_name = "hostonly-net"
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

}

data "external" "vm_ips" {
  for_each = { for vm in var.vm_name : vm.name => vm }
  depends_on = [libvirt_domain.vms]

  program = ["bash", "-c", <<EOT
    for i in {1..10}; do
      ip=$(virsh domifaddr ${each.key} | grep -m1 ipv4 | awk '{print $4}' | cut -d'/' -f1)
      if [ -n "$ip" ]; then
        echo "{\"output\": \"$ip\"}"
        exit 0
      fi
      sleep 60  # Wait before retrying
    done
    echo '{"output": ""}'  # Return an empty string if no IP found after retries
  EOT
  ]
}


# Output the IP addresses for all VMs
output "vm_ips" {
  value = { for vm in var.vm_name : vm.name => data.external.vm_ips[vm.name].result["output"] }
}


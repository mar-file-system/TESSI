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

# Define a variable list for hosts
variable "hosts" {
  type = map(string)
  default = {
    "in07" = "qemu+ssh://root@in07/system"
    "in16" = "qemu+ssh://root@in16/system"
  }
}

# Provider blocks for each host
provider "libvirt" {
  alias = "in07"
  uri   = "qemu+ssh://root@in07/system"
}

provider "libvirt" {
  alias = "in16"
  uri   = "qemu+ssh://root@in16/system"
}

/*
# Create bridge network for in07
resource "libvirt_network" "in07_bridge" {
  name      = "in07_bridge"
  mode      = "bridge"
  bridge    = "in07_br0"  # Custom bridge name
  autostart = true
  provider  = libvirt.in07  # Use in07 provider
}

# Create bridge network for in16
resource "libvirt_network" "in16_bridge" {
  name      = "in16_bridge"
  mode      = "bridge"
  bridge    = "in16_br0"  # Custom bridge name
  autostart = true
  provider  = libvirt.in16  # Use in16 provider
}
*/

# Execute virsh list --all for each host using a loop
resource "null_resource" "list_vms" {
  for_each = var.hosts

  provisioner "local-exec" {
    # Run the regular SSH command without qemu+ssh for virsh
    command = "ssh -o StrictHostKeyChecking=no root@${each.key} 'virsh list --all; exit'"
  }

  # this won't run multiple times since a null_resource is basically a noop.
  # we can destroy first and then apply or we can use this trigger to force it everytime
  triggers = {
    always_run = "${timestamp()}"  # Ensure this runs on every apply
  }
}

# Query networks on each host
resource "null_resource" "list_networks" {
  for_each = var.hosts

  provisioner "local-exec" {
    # Run the virsh net-list --all command to list networks
    command = "ssh -o StrictHostKeyChecking=no root@${each.key} 'virsh net-list --all; exit'"
  }

  triggers = {
    always_run = "${timestamp()}"  # Ensure this runs on every apply
  }
}



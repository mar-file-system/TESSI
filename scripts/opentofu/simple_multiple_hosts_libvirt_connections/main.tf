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

# Provider blocks for each host
provider "libvirt" {
  alias = "in07"
  uri   = "qemu+ssh://root@in07/system"
}

provider "libvirt" {
  alias = "in16"
  uri   = "qemu+ssh://root@in16/system"
}

# Resource to execute virsh list --all on in07
resource "null_resource" "list_in07" {
  provisioner "local-exec" {
    command = "ssh -o StrictHostKeyChecking=no root@in07 'virsh -c qemu:///system list --all; exit'"
  }
}

# Resource to execute virsh list --all on in16
resource "null_resource" "list_in16" {
  provisioner "local-exec" {
    command = "ssh -o StrictHostKeyChecking=no root@in16 'virsh -c qemu:///system list --all; exit'"
  }
}


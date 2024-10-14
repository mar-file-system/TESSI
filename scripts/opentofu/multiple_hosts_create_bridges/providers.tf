# Provider blocks for each host
provider "libvirt" {
  alias = "in07"
  uri   = "qemu+ssh://root@in07/system"
}

provider "libvirt" {
  alias = "in16"
  uri   = "qemu+ssh://root@in16/system"
}


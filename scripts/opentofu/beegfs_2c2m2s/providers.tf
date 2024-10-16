# Provider blocks for each host
provider "libvirt" {
  alias = "in07"
  uri   = "qemu+ssh://root@in07/system"
}

provider "libvirt" {
  alias = "in16"
  uri   = "qemu+ssh://root@in16/system"
}

# Define a variable list for hosts
variable "hosts" {
  type = map(string)
  default = {
    "in07" = "qemu+ssh://root@in07/system"
    "in16" = "qemu+ssh://root@in16/system"
  }
}

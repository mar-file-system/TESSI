
variable "vm_name" {
  type = list(object({
    name             = string
    machine          = optional(string, "pc-q35-rhel8.2.0")
    memory           = optional(string, "2048")
    vcpu             = optional(number, 2)
    second_disk_size = optional(number, null)
    host             = string  # The short-hand for the host (e.g., "in07" or "in16")
    source_image     = optional(string, "/var/lib/libvirt/images/gold-beegfs-almalinux8-server.qcow2")  # Optional source image with default
    storage_pool     = optional(string, "default")
    network          = optional(string, "wireguard-virt")
    #network          = optional(string, "vm-net")
  }))
  default = [
    {
      name            = "beegfs-client00"
      host            = "in07"
    },
    {
      name            = "beegfs-client01"
      host            = "in07"
    },
    {
      name            = "beegfs-meta00"
      second_disk_size = 5
      host            = "in07"
    },
    {
      name            = "beegfs-meta01"
      second_disk_size = 5
      host            = "in16"
    },
    {
      name            = "beegfs-data00"
      second_disk_size = 10
      host            = "in16"
    },
    {
      name            = "beegfs-data01"
      second_disk_size = 10
      host            = "in16"
    }
  ]
}


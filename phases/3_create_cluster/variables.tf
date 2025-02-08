variable "vm_name" {
  description = "List of VM definitions"
  type = list(object({
    name             = string
    machine          = string 
    memory           = string 
    vcpu             = string 
    second_disk_size = optional(number, null)
    host             = string
    source_image     = string 
    storage_pool     = string 
    netone           = string 
    nettwo           = string 
    mac_address      = string
    cloudinit        = optional(string, "")
  }))
}

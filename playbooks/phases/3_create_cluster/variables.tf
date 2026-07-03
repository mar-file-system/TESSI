variable "vm_name" {
  description = "List of VM definitions"
  type = list(object({
    name                    = string
    machine                 = string 
    memory                  = string 
    vcpu                    = string 
    extra_hdds              = optional(list(object({ size = number, label = string })), []) 
    host                    = string
    source_image            = string 
    storage_pool            = string 
    storage_pool_path       = string
    netone                  = string 
    nettwo                  = string 
    mac_address             = string
    cloudinit_user_data     = optional(string, "")
    cloudinit_network       = optional(string, "")
  }))
  default = []  # try to set an empty default so that init works without a var-file passed 
}

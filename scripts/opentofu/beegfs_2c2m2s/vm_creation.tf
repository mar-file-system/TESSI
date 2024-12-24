resource "libvirt_domain" "in07_vms" {
  provider = libvirt.in07
  for_each   = { for vm in var.vm_name : vm.name => vm if vm.host == "in07"}
  name       = "${each.value.name}"
  memory     = each.value.memory  # Default memory if not specified
  vcpu       = each.value.vcpu    # Default vCPU if not specified
  running    = true
  autostart  = true
  machine    = each.value.machine

  # Attach primary disk
  disk {
    volume_id = libvirt_volume.in07_volumes[each.key].id
  }

  # Attach secondary disk if it exists
  dynamic "disk" {
    for_each = (each.value.second_disk_size != null) ? [1] : []
    content {
      volume_id = libvirt_volume.in07_second_volumes[each.key].id
    }
  }

  network_interface {
    network_name = each.value.network
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

  # Ensure each domain waits for all volumes
  # it'd be more parallel to have each VM wait on only its own volumes but that is hard since some have two volumes and some have just one
  #   and depends_on only works on static lists so we can't create conditional dependencies
  depends_on = [
    libvirt_volume.in07_volumes,
    libvirt_volume.in07_second_volumes,
  ]

}

resource "libvirt_domain" "in16_vms" {
  provider = libvirt.in16
  for_each   = { for vm in var.vm_name : vm.name => vm if vm.host == "in16"}
  name       = "${each.value.name}"
  memory     = each.value.memory  # Default memory if not specified
  vcpu       = each.value.vcpu    # Default vCPU if not specified
  running    = true
  autostart  = true
  machine    = each.value.machine

  # Attach primary disk
  disk {
    volume_id = libvirt_volume.in16_volumes[each.key].id
  }

  # Attach secondary disk if it exists
  dynamic "disk" {
    for_each = (each.value.second_disk_size != null) ? [1] : []
    content {
      volume_id = libvirt_volume.in16_second_volumes[each.key].id
    }
  }

  network_interface {
    network_name = each.value.network
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

  # Ensure each domain waits for all volumes
  # it'd be more parallel to have each VM wait on only its own volumes but that is hard since some have two volumes and some have just one
  #   and depends_on only works on static lists so we can't create conditional dependencies
  depends_on = [
    libvirt_volume.in16_volumes,
    libvirt_volume.in16_second_volumes,
  ]

}

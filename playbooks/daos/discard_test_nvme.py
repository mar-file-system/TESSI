#!/usr/bin/env python3
"""Discard only saved TESSI NVMe namespaces after full-system cleanup stops DAOS."""
import json
from pathlib import Path
import re
import subprocess


def run(argv):
    return subprocess.check_output(argv, text=True)


addresses = json.loads(Path('/etc/daos/tessi_nvme.json').read_text())
assert isinstance(addresses, list) and addresses, 'Missing saved PCI mapping'
assert len(addresses) == len(set(addresses)), 'Duplicate saved PCI addresses'
for address in addresses:
    assert re.fullmatch(r'[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]', address), 'Invalid saved PCI address'
    pci = Path('/sys/bus/pci/devices') / address
    assert (pci/'class').read_text().strip().startswith('0x0108'), 'Saved device is not NVMe'
    assert (pci/'driver').resolve().name == 'nvme', 'Reset controllers to kernel NVMe first'
state = subprocess.run(['systemctl', 'is-active', 'daos_server'], text=True, capture_output=True)
assert state.stdout.strip() == 'inactive', 'DAOS must be stopped before discarding storage'
by_pci = {}
for block in Path('/sys/class/block').iterdir():
    if not re.fullmatch(r'nvme\d+n\d+', block.name):
        continue
    controller = block.name.rsplit('n', 1)[0]
    pci = (Path('/sys/class/nvme')/controller/'device').resolve().name
    if pci in addresses:
        by_pci.setdefault(pci, []).append('/dev/'+block.name)
assert set(by_pci) == set(addresses), 'Not all saved controllers have kernel namespaces'
assert all(len(names) == 1 for names in by_pci.values()), 'Expected one namespace per saved controller'
# Validate every device BEFORE discarding any. Never discard mounted devices,
# mounted children, swap, partitions or devices held by another storage driver.
swaps = {str(Path(line.split()[0]).resolve()) for line in Path('/proc/swaps').read_text().splitlines()[1:]}
devices = [by_pci[address][0] for address in addresses]
for device in devices:
    disks = json.loads(run(['lsblk', '--json', '--output', 'PATH,TYPE,MOUNTPOINTS', device]))['blockdevices']
    assert len(disks) == 1 and disks[0]['type'] == 'disk', 'Expected a whole raw namespace: '+device
    disk = disks[0]
    assert not disk.get('children') and not any(disk.get('mountpoints') or []), 'Device is partitioned, mounted or held: '+device
    assert str(Path(device).resolve()) not in swaps, 'Device is swap: '+device
    assert not list((Path('/sys/class/block')/Path(device).name/'holders').iterdir()), 'Device has active holders: '+device
    print('Validated benchmark namespace:', device, flush=True)
for device in devices:
    # No partial-signature-wipe fallback: DAOS/SPDK metadata may be anywhere.
    # Unsupported discard fails the cleanup and no clean marker is written.
    subprocess.run(['blkdiscard', '--force', device], check=True)
    print('Discarded benchmark namespace:', device, flush=True)

#!/usr/bin/env python3

import argparse
import yaml
import re
from itertools import count

def expand_hosts(expr):
    """
    hs[145-160] -> ['hs145', 'hs146', ...]
    """
    m = re.match(r'(.*)\[(\d+)-(\d+)\]', expr)
    if not m:
        return [expr]

    prefix, start, end = m.groups()
    return [f"{prefix}{i}" for i in range(int(start), int(end) + 1)]

def make_uniform_vms(hosts, vm_count, group, start_ip):
    result = {}

    ip = start_ip
    for host in hosts:
        vms = []
        for _ in range(vm_count):
            name = f"n{ip:02d}"
            vms.append([name, f"{{{{ vm_groups.{group} }}}}", [], ip+1])
            ip += 1
        result[host] = {"vms": vms}

    return result


def make_mixed_vms(hosts, layout, start_ip):
    """
    layout example:
    [
      ("mds", "mds_group", [10,10]),
      ("oss", "oss_group", [10]),
      ("cli", "cli_group", [])
    ]
    """
    ip = count(start_ip)
    counters = {role: count(0) for role, _, _ in layout}
    result = {}

    for host in hosts:
        vms = []
        for role, group, disks in layout:
            idx = next(counters[role])
            name = f"{role}{idx:02d}"
            vms.append([name, f"{{{{ vm_groups.{group} }}}}", disks, next(ip)])
        result[host] = {"vms": vms}

    return result

def print_inventory(hosts_data):
    print("  children:")
    print("    physical_hosts:")
    print("      hosts:")

    for host, data in hosts_data.items():
        print(f"        {host}:")
        print(f"          vms:")
        for name, group, disks, ip in data["vms"]:
            disks_str = (
                "[" + ",".join(str(d) for d in disks) + "]"
                if disks else "[]"
            )
            print(
                f'            - [ {name}, "{group}", {disks_str}, {ip} ]'
            )


def main():
    epilog = """
EXAMPLES

1) Uniform nodes
----------------
Create hs145–hs160, each with 4 VMs in node_group and no extra disks:

  python gen_vms.py \\
    --hosts hs[145-160] \\
    --mode uniform \\
    --vm-count 4 \\
    --group node_group

2) Mixed roles on a subset
--------------------------
On hs145–hs147, create one MDS, OSS, and CLI per host:

  python gen_vms.py \\
    --hosts hs[145-147] \\
    --mode mixed \\
    --layout \\
      mds:mds_group:10,10 \\
      oss:oss_group:10 \\
      cli:cli_group

Then on hs148–hs160, create 4 clients per host:

  python gen_vms.py \\
    --hosts hs[148-160] \\
    --mode uniform \\
    --vm-count 4 \\
    --group cli_group \\
    --start-ip 100
"""

    p = argparse.ArgumentParser(
        description="Generate VM inventory YAML for physical hosts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog
    )

    p.add_argument("--hosts", required=True, help="e.g. hs[145-160]")
    p.add_argument("--mode", choices=["uniform", "mixed"], required=True)

    # uniform mode
    p.add_argument("--vm-count", type=int, help="VMs per host (uniform mode)")
    p.add_argument("--group", help="vm_groups.<group> (uniform mode)")

    # mixed mode
    p.add_argument(
        "--layout",
        nargs="+",
        help="role:group:disk,disk   (disk list optional, mixed mode)"
    )

    p.add_argument("--start-ip", type=int, default=0)

    args = p.parse_args()

    hosts = expand_hosts(args.hosts)

    if args.mode == "uniform":
        if args.vm_count is None or args.group is None:
            p.error("uniform mode requires --vm-count and --group")

        hosts_data = make_uniform_vms(
            hosts,
            args.vm_count,
            args.group,
            args.start_ip
        )

    else:
        if not args.layout:
            p.error("mixed mode requires --layout")

        layout = []
        for spec in args.layout:
            parts = spec.split(":")
            role = parts[0]
            group = parts[1]
            disks = list(map(int, parts[2].split(","))) if len(parts) == 3 else []
            layout.append((role, group, disks))

        hosts_data = make_mixed_vms(
            hosts,
            layout,
            args.start_ip
        )

    print_inventory(hosts_data)


if __name__ == "__main__":
    main()


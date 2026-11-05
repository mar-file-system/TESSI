#!/usr/bin/env python3
"""Raw SSD and MPI network baselines. No installation or device formatting."""
import argparse
import concurrent.futures
import datetime
import itertools
import json
import os
import pathlib
import re
import subprocess
import sys
import time


def run(argv, timeout=120):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{argv!r}: rc={result.returncode}\n{result.stdout}\n{result.stderr}')
    return result.stdout


def check_devices(devices):
    if not devices or len(set(devices)) != len(devices):
        raise ValueError('Specify a nonempty, unique local_storage_devices list')
    # Fail rather than silently testing mounted storage or an initialized DAOS.
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'daos_server'],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        raise ValueError('Stop DAOS before measuring raw devices; use a fresh allocation before DAOS initialization')
    resolved = [os.path.realpath(d) for d in devices]
    if len(set(resolved)) != len(resolved):
        raise ValueError('Device aliases resolve to duplicate block devices')
    inventory = []
    for device in devices:
        if not device.startswith('/dev/'):
            raise ValueError(f'Not a /dev block device: {device}')
        tree = json.loads(run(['lsblk', '--json', '--bytes', '--output',
                               'PATH,TYPE,SIZE,MOUNTPOINTS,FSTYPE,MODEL,SERIAL', device]))['blockdevices']
        if len(tree) != 1 or tree[0]['type'] != 'disk':
            raise ValueError(f'Expected a whole raw disk: {device}')
        disk = tree[0]
        if disk.get('children') or any(disk.get('mountpoints') or []) or disk.get('fstype'):
            raise ValueError(f'{device} has partitions, a filesystem signature, or mounts; refusing writes')
        # Swap may be active without a regular mountpoint.
        swaps = pathlib.Path('/proc/swaps').read_text().splitlines()[1:]
        if any(os.path.realpath(line.split()[0]) == os.path.realpath(device) for line in swaps):
            raise ValueError(f'{device} is active swap')
        inventory.append(disk)
    return inventory


def measure_fio(config, devices, output):
    if config.get('allow_destructive_writes') is not True:
        raise ValueError('Raw FIO writes require system.performance.allow_destructive_writes: true')
    disks = check_devices(devices)
    records = []
    for rw, block in [('write', '1M'), ('read', '1M'), ('randwrite', '4k'), ('randread', '4k')]:
        argv = ['/usr/local/bin/fio', '--output-format=json', '--ioengine=libaio',
                '--direct=1', '--time_based=1', '--numjobs=1', '--thread=1',
                '--allow_file_create=0', '--group_reporting=0',
                f"--runtime={int(config['fio_runtime_seconds'])}",
                f"--ramp_time={int(config['fio_ramp_seconds'])}",
                f"--iodepth={int(config['fio_iodepth'])}",
                f"--size={config['fio_size_per_device']}", f'--rw={rw}', f'--bs={block}']
        # One concurrent job per SSD; all servers also run concurrently.
        for index, device in enumerate(devices):
            argv += [f'--name=device-{index}', f'--filename={device}']
        raw = json.loads(run(argv, int(config['command_timeout_seconds'])))
        if not raw.get('jobs') or any(job.get('error', 0) for job in raw['jobs']):
            raise RuntimeError(f'FIO {rw} failed: {raw}')
        direction = 'write' if 'write' in rw else 'read'
        records.append({'workload': rw, 'block_size': block, 'command': argv,
                        'bandwidth_bytes_per_second': sum(j[direction]['bw_bytes'] for j in raw['jobs']),
                        'iops': sum(j[direction]['iops'] for j in raw['jobs']), 'raw': raw})
        (output / f'fio-{rw}.json').write_text(json.dumps(raw, indent=2) + '\n')
    return {'devices': disks, 'measurements': records,
            'note': 'Time-based raw region tests, not a full-device steady-state preconditioning study.'}


def measure_network_role(config, topology, output, mpi, tag_prefix=""):
    # Ansible's shared tasks supply the MPI launcher and OSU installation path.
    # This runner only schedules pairs, chooses rank placement and records data.
    prefix = str(pathlib.Path(mpi['osu_binary_dir']) / 'mpi' / 'pt2pt') + '/'
    launcher = mpi['launcher_argv']
    if not isinstance(launcher, list) or not launcher:
        raise ValueError('MPI launcher must be supplied by the shared Ansible task')
    clients, servers = topology['clients'], topology['ds']
    # Cross-role links plus storage-to-storage links used for replication.
    pairs = list(itertools.product(clients, servers)) + list(itertools.combinations(servers, 2))
    timeout = int(config['command_timeout_seconds'])
    maximum = int(config['osu_max_message_bytes'])
    def one(pair, benchmark, tag):
        binary = prefix + benchmark
        argv = launcher + [
                '--host', ','.join(h + ':1' for h in pair), '-np', '2',
                '--map-by', 'ppr:1:node', binary, '-m', f'1:{maximum}',
                '-i', str(int(config['osu_iterations'])),
                '-x', str(int(config['osu_warmup_iterations']))]
        text = run(argv, timeout)
        tag = tag_prefix + tag
        (output / f'{tag}.txt').write_text(text)
        rows = []
        for line in text.splitlines():
            columns = line.split()
            if len(columns) >= 2 and columns[0].isdigit():
                rows.append({'message_bytes': int(columns[0]), 'value': float(columns[1])})
        if not rows:
            raise ValueError(f'No OSU measurements in {tag}: {text}')
        return {'hosts': pair, 'benchmark': benchmark, 'command': argv,
                'unit': 'MB/s' if benchmark == 'osu_bw' else 'microseconds',
                'samples': rows, 'raw': text, 'artifact': f'{tag}.txt'}
    # Enforce RDMA; never silently report TCP numbers as an IB baseline.
    os.environ['UCX_TLS'] = 'rc,sm,self'
    records = []
    for i, pair in enumerate(pairs):
        for benchmark in ['osu_latency', 'osu_bw']:
            records.append(one(pair, benchmark, f'pair-{i}-{benchmark}'))
    # Independent node-disjoint pairs launched together, one rank per node.
    # Sum is a concurrent-pair measurement, not an assumed all-to-all ceiling.
    concurrent_pairs = list(zip(clients, servers))
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(concurrent_pairs)) as pool:
        futures = [pool.submit(one, pair, 'osu_bw', f'concurrent-{i}-osu_bw')
                   for i, pair in enumerate(concurrent_pairs)]
        simultaneous = [future.result() for future in futures]
    last_size = {r['samples'][-1]['message_bytes'] for r in simultaneous}
    if len(last_size) != 1:
        raise ValueError('Concurrent OSU jobs did not use identical message sizes')
    return {'transport': 'Open MPI UCX, UCX_TLS=rc,sm,self', 'pairwise': records,
            'concurrent_pairs': simultaneous,
            'concurrent_bandwidth_MB_per_second': sum(r['samples'][-1]['value'] for r in simultaneous),
            'concurrent_message_bytes': last_size.pop(),
            'unpaired_clients': clients[len(concurrent_pairs):],
            'unpaired_servers': servers[len(concurrent_pairs):],
            'note': 'Independent concurrent OSU sweeps; large-message samples approximate overlapping steady traffic, without a global MPI barrier.'}


def measure_network(config, topology, output, mpi):
    result = measure_network_role(config, topology, output, mpi)
    if topology.get('mds'):
        result['metadata'] = measure_network_role(
            config, {'clients': topology['clients'], 'ds': topology['mds']},
            output, mpi, tag_prefix='metadata-')
        result['role_measurement_note'] = (
            'Data and metadata network sweeps run separately; shared client NIC/fabric '
            'ceilings cannot be added as simultaneously achievable throughput.')
    return result


def manifest(payload, output):
    hosts = payload['hosts']
    storage = {}
    storage_by_role = {}
    for name, host in hosts.items():
        role = 'ds' if name in payload['groups'].get('ds', []) else 'mds' if name in payload['groups'].get('mds', []) else None
        if role is None:
            continue
        role_storage = storage_by_role.setdefault(role, {})
        for measurement in host.get('fio', {}).get('measurements', []):
            metric = role_storage.setdefault(measurement['workload'], {'bandwidth_bytes_per_second': 0, 'iops': 0})
            metric['bandwidth_bytes_per_second'] += measurement['bandwidth_bytes_per_second']
            metric['iops'] += measurement['iops']
    storage = storage_by_role.get('ds', {})
    payload.update(storage_aggregate_by_role=storage_by_role, architecture='split' if payload['groups'].get('mds') else 'shared', schema_version=1, measured_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   storage_aggregate=storage,
                   interpretation='Storage aggregates sum simultaneously launched server jobs. These are measured component baselines, not guaranteed DAOS ceilings. Metadata comparisons assume one metadata operation per I/O; data and metadata ceilings share client NIC/fabric resources and must not be added.')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'manifest.json').write_text(json.dumps(payload, indent=2) + '\n')
    lines = [f'Performance baseline: {payload["system_id"]}', f'Manifest: {output / "manifest.json"}']
    for role, workloads in storage_by_role.items():
        for workload, metric in workloads.items():
            lines.append(f'FIO {role} {workload}: {metric["bandwidth_bytes_per_second"] / 2**30:.3f} GiB/s, {metric["iops"]:.0f} IOPS')
    lines.append(f'OSU concurrent client/server pairs: {payload["network"]["concurrent_bandwidth_MB_per_second"]:.3f} MB/s')
    (output / 'summary.txt').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['check', 'fio', 'network', 'manifest'])
    parser.add_argument('--output', default='.')
    args = parser.parse_args()
    data = json.load(sys.stdin)
    output = pathlib.Path(args.output)
    if args.mode == 'manifest':
        manifest(data, output)
        return
    output.mkdir(parents=True, exist_ok=True)
    if args.mode == 'check':
        result = check_devices(data['devices'])
    elif args.mode == 'fio':
        result = measure_fio(data['config'], data['devices'], output)
    else:
        result = measure_network(data['config'], data['topology'], output, data['mpi'])
    print(json.dumps(result))


if __name__ == '__main__':
    main()

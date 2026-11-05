#!/usr/bin/env python3
"""Report from immutable baseline samples; no node access or benchmark execution.

Uses the existing Graphviz -> PostScript -> Ghostscript PDF toolchain. The only
Python dependency is Jinja2, already required by the Ansible report controller.
"""
import argparse
import sys
import datetime
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import tempfile
import textwrap

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shared/files'))
from tessi_report_common import (GIB, Pages, stats, short_name, format_bw, format_iops,
                                 atomic_json, render_topology, write_pdf, TOPOLOGY_TEMPLATE)

WORKLOADS = ('write', 'read', 'randwrite', 'randread')
LABELS = {'write': 'Sequential write (1 MiB)', 'read': 'Sequential read (1 MiB)',
          'randwrite': 'Random write (4 KiB)', 'randread': 'Random read (4 KiB)'}



def derive_role(data):
    storage = {}
    totals = {}
    capacity = {}
    for host in data['groups']['ds']:
        detail = data['hosts'][host]
        devices = detail.get('fio', {}).get('devices', [])
        if devices:
            capacity[host] = sum(int(d['size']) for d in devices)
        for row in detail.get('fio', {}).get('measurements', []):
            workload = row['workload']
            metrics = storage.setdefault(workload, {'bandwidth_bytes_per_second': {}, 'iops': {}})
            for metric in metrics:
                metrics[metric][host] = float(row[metric])
    for workload in WORKLOADS:
        if workload not in storage or set(storage[workload]['iops']) != set(data['groups']['ds']):
            raise ValueError(f'Incomplete FIO workload {workload}; cannot estimate cluster capacity')
        totals[workload] = {metric: sum(values.values()) for metric, values in storage[workload].items()}
    node_stats = {w: {metric: stats(values) for metric, values in metrics.items()}
                  for w, metrics in storage.items()}
    concurrent = data['network'].get('concurrent_pairs', [])
    if not concurrent:
        raise ValueError('No concurrent OSU measurements; cannot estimate aggregate network capacity')
    common_sizes = set.intersection(*[{int(s['message_bytes']) for s in r['samples']} for r in concurrent])
    curve = []
    for size in sorted(common_sizes):
        if size <= 0:
            continue
        bw = sum(next(float(s['value']) for s in r['samples'] if int(s['message_bytes']) == size)
                 * 1_000_000 for r in concurrent)
        curve.append({'message_bytes': size, 'bandwidth_bytes_per_second': bw,
                      'message_rate_per_second': bw / size})
    if not curve:
        raise ValueError('Concurrent OSU jobs have no common message sizes')
    best_bw = max(curve, key=lambda row: row['bandwidth_bytes_per_second'])
    best_rate = max(curve, key=lambda row: row['message_rate_per_second'])
    at_4k = next((row for row in curve if row['message_bytes'] == 4096), None)
    network_bw = best_bw['bandwidth_bytes_per_second']
    network_iops = at_4k['message_rate_per_second'] if at_4k else None
    storage_bw = max(totals[w]['bandwidth_bytes_per_second'] for w in ('read', 'write'))
    storage_iops = max(totals[w]['iops'] for w in ('randread', 'randwrite'))
    def ceiling(storage_value, network_value):
        if network_value is None:
            return {'value': None, 'bottleneck': 'unavailable'}
        return {'value': min(storage_value, network_value),
                'bottleneck': 'storage' if storage_value < network_value else
                              'network' if network_value < storage_value else 'balanced'}
    bw_limit, iops_limit = ceiling(storage_bw, network_bw), ceiling(storage_iops, network_iops)
    directional = {}
    for direction, seq, rnd in [('read', 'read', 'randread'), ('write', 'write', 'randwrite')]:
        directional[direction] = {
            'storage_bandwidth_bytes_per_second': totals[seq]['bandwidth_bytes_per_second'],
            'storage_iops_4KiB': totals[rnd]['iops'],
            'cluster_bandwidth': ceiling(totals[seq]['bandwidth_bytes_per_second'], network_bw),
            'cluster_iops_4KiB': ceiling(totals[rnd]['iops'], network_iops)}
    pairwise = data['network'].get('pairwise', [])
    latency = {}
    pair_bw = {}
    for row in pairwise:
        key = ' -> '.join(row['hosts'])
        if row['benchmark'] == 'osu_latency' and row['samples']:
            sample = min(row['samples'], key=lambda r: int(r['message_bytes']))
            latency[key] = float(sample['value'])
        elif row['benchmark'] == 'osu_bw' and row['samples']:
            pair_bw[key] = max(float(r['value']) * 1_000_000 for r in row['samples'])
    fio_versions, osu_versions = set(), set()
    for detail in data['hosts'].values():
        fio_versions.update(v for v in detail.get('software_versions', []) if re.match(r'^fio[- ]', v))
    for row in pairwise + concurrent:
        osu_versions.update(re.findall(r'OSU[^\n]*?\bv([0-9][\w.-]*)', row.get('raw', '')))
    return {
        'schema_version': 1, 'calculated_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'method': 'Component-limited estimate: min(storage, network); measured throughput is a proxy, not a proven hardware upper bound.',
        'units': {'bandwidth': 'bytes/second', 'iops': 'operations/second',
                  'network_message_rate': 'one-way messages/second', 'latency': 'microseconds',
                  'capacity': 'bytes', 'stddev': 'population (across storage nodes, not repeated runs)'},
        'assumptions': [
            'Storage bandwidth uses the faster aggregate sequential read/write workload; storage IOPS uses the faster aggregate 4KiB random read/write workload.',
            'Network bandwidth is the highest sum of concurrent-pair OSU bandwidth at a common message size (decimal MB/s converted to bytes/s).',
            'Network IOPS is a 4096-byte message-rate proxy: sum(concurrent OSU BW at 4096 bytes) / 4096. It is not measured storage or DAOS IOPS.',
            'One logical operation is assumed to transfer one 4KiB network message; request, reply, protocol, replication and DAOS overhead are excluded.',
            'Only client-to-server direction was measured. Read estimates assume the same bandwidth in reverse; full duplex was not measured.',
            'Independent concurrent OSU sweeps are not barrier-synchronized. Aggregate values approximate overlapping traffic.',
            'Unpaired nodes do not contribute to the measured concurrent network sum; do not extrapolate linearly.',
            'FIO is a short, time-based region test with direct I/O, not full-device steady-state preconditioning. Capacity is raw, not usable DAOS capacity.',
            'Metadata comparisons assume one metadata operation per I/O; real metadata operations may require multiple I/Os. Cross-node stddev does not estimate run-to-run uncertainty.'
        ],
        'environment': {'fio_versions': sorted(fio_versions), 'osu_versions': sorted(osu_versions)},
        'capacity': {'total_storage_bytes': sum(capacity.values()), 'per_node_bytes': capacity,
                     'total_storage_devices': sum(len(data['hosts'][h].get('fio', {}).get('devices', [])) for h in data['groups']['ds'])},
        'storage': {'aggregate_by_workload': totals, 'per_node_statistics': node_stats,
                    'estimated_max_aggregate_bandwidth_bytes_per_second': storage_bw,
                    'estimated_max_aggregate_iops_4KiB': storage_iops},
        'network': {'concurrent_pairs_count': len(concurrent), 'aggregate_curve': curve,
                    'estimated_max_aggregate_bandwidth_bytes_per_second': network_bw,
                    'bandwidth_peak_message_bytes': best_bw['message_bytes'],
                    'estimated_aggregate_iops_proxy_4KiB': network_iops,
                    'maximum_message_rate_per_second': best_rate['message_rate_per_second'],
                    'maximum_message_rate_message_bytes': best_rate['message_bytes'],
                    'pairwise_peak_bandwidth_statistics': stats(pair_bw),
                    'small_message_latency_statistics': stats(latency),
                    'unpaired_clients': data['network'].get('unpaired_clients', []),
                    'unpaired_servers': data['network'].get('unpaired_servers', [])},
        'cluster': {'estimated_max_aggregate_bandwidth_bytes_per_second': bw_limit['value'],
                    'bandwidth_bottleneck': bw_limit['bottleneck'],
                    'estimated_max_aggregate_iops_4KiB': iops_limit['value'],
                    'iops_bottleneck': iops_limit['bottleneck'], 'by_direction': directional}}


def derive(data):
    # Preserve the existing data-plane schema for DAOS and existing consumers.
    result = derive_role(data)
    result['architecture'] = 'split' if data['groups'].get('mds') else 'shared'
    result['planes'] = {'data': {key: result[key] for key in
                              ('capacity', 'storage', 'network', 'cluster')}}
    if data['groups'].get('mds'):
        if not data['network'].get('metadata'):
            raise ValueError('Split MDS/DS baseline needs MDS FIO and client/MDS OSU samples; rerun phase1 and phase6')
        scoped = dict(data)
        scoped['groups'] = dict(data['groups'], ds=data['groups']['mds'])
        scoped['network'] = data['network']['metadata']
        metadata = derive_role(scoped)
        result['planes']['metadata'] = {key: metadata[key] for key in
                                       ('capacity', 'storage', 'network', 'cluster')}
        result['assumptions'].append(
            'Data and metadata ceilings are isolated-workload estimates. Shared client NICs '
            'and fabric prevent adding them as simultaneously achievable rates.')
    return result


def select_manifest(root, groups, pointer=None):
    def matches(path):
        data = json.loads(path.read_text())
        return all(sorted(data.get('groups', {}).get(role, [])) == sorted(groups.get(role, []))
                   for role in ('ds', 'clients', 'mds'))
    if pointer and Path(pointer).is_file():
        candidate = Path(Path(pointer).read_text().strip())
        if candidate.is_file() and matches(candidate):
            return candidate
    candidates = []
    for path in Path(root).glob('*/*/manifest.json'):
        if matches(path):
            data = json.loads(path.read_text())
            candidates.append((data.get('measured_at_utc', ''), str(path), path))
    if not candidates:
        raise ValueError('No completed performance manifest for this inventory; run phase6 or pass performance_manifest_path explicitly')
    return max(candidates)[2]



def report_pages(data, derived, eps):
    p = Pages()
    p.page('Performance baseline', 'TESSI / INFRASTRUCTURE PROFILE')
    p.paragraph(f"{len(data['groups']['ds'])} storage servers  /  {len(data['groups']['clients'])} clients  /  {derived['capacity']['total_storage_devices']} SSDs", size=12)
    p.paragraph('Measured: ' + data['measured_at_utc'], size=9)
    p.embed_eps(eps, 32, 158, 548, 462)
    p.text(42, 131, 'Logical fabric view - actual switch paths were not discovered.', 9)
    p.text(42, 112, 'Node labels preserve allocation aliases, physical names and IB addresses.', 9)
    for i, line in enumerate(textwrap.wrap(data['system_id'], 95)):
        p.text(42, 82-i*12, line, 8)

    p.page('System and measurement summary')
    hosts = list(data['hosts'].values())
    env = derived['environment']
    values = [
        ('Kernel', ', '.join(sorted({h['kernel'] for h in hosts}))),
        ('OS', ', '.join(sorted({h['os'] + ' ' + h['os_version'] for h in hosts}))),
        ('Architecture', ', '.join(sorted({h['architecture'] for h in hosts}))),
        ('FIO version', ', '.join(env['fio_versions']) or 'Not recorded'),
        ('OSU version', ', '.join(env['osu_versions']) or 'Not recorded'),
        ('Raw storage capacity', f"{derived['capacity']['total_storage_bytes']/2**40:,.3f} TiB ({derived['capacity']['total_storage_bytes']:,} bytes)"),
        ('Storage devices', derived['capacity']['total_storage_devices']),
        ('Network', data['network']['transport']),
        ('CPU models', ', '.join(sorted({s for h in hosts for s in h.get('cpu', []) if 'CPU' in s}))),
        ('RAM per node', ', '.join(sorted({f"{h['memory_MiB']/1024:.1f} GiB" for h in hosts}))),
        ('Logical CPUs per node', ', '.join(map(str, sorted({h['vcpus'] for h in hosts})))),
        ('FIO time / ramp', f"{data['config']['fio_runtime_seconds']}s / {data['config']['fio_ramp_seconds']}s per workload"),
        ('FIO region / depth', f"{data['config']['fio_size_per_device']} per device / queue depth {data['config']['fio_iodepth']}"),
        ('FIO concurrency', 'One job per SSD; all storage servers launched concurrently'),
        ('OSU samples', f"{data['config']['osu_iterations']} iterations; {data['config']['osu_warmup_iterations']} warmup"),
        ('Concurrent network pairs', derived['network']['concurrent_pairs_count']),
    ]
    for key, value in values:
        if p.y < 90:
            p.page('System summary (continued)')
        p.kv(key, value)
    versions = sorted({s for h in hosts for s in h.get('software_versions', []) if s.startswith(('openmpi-', 'ucx-', 'doca-ofed-'))})
    p.kv('MPI / UCX packages', ', '.join(versions))

    p.page('Estimated cluster ceilings')
    p.paragraph('Component-limited model: cluster = min(storage, network). These are estimates from measured component throughput, not proven theoretical hardware limits.')
    p.kv('Storage bandwidth', format_bw(derived['storage']['estimated_max_aggregate_bandwidth_bytes_per_second']))
    p.kv('Network bandwidth', format_bw(derived['network']['estimated_max_aggregate_bandwidth_bytes_per_second']))
    p.kv('Cluster bandwidth', format_bw(derived['cluster']['estimated_max_aggregate_bandwidth_bytes_per_second']) + ' | bottleneck: ' + derived['cluster']['bandwidth_bottleneck'])
    p.y -= 12
    p.kv('Storage IOPS (4 KiB)', format_iops(derived['storage']['estimated_max_aggregate_iops_4KiB']))
    p.kv('Network IOPS proxy', format_iops(derived['network']['estimated_aggregate_iops_proxy_4KiB']))
    p.kv('Cluster IOPS estimate', format_iops(derived['cluster']['estimated_max_aggregate_iops_4KiB']) + ' | bottleneck: ' + derived['cluster']['iops_bottleneck'])
    p.y -= 10
    p.paragraph('Read / write estimates', size=12)
    for direction, row in derived['cluster']['by_direction'].items():
        p.kv(direction.capitalize(), format_bw(row['cluster_bandwidth']['value']) + ' | ' + format_iops(row['cluster_iops_4KiB']['value']))
    p.paragraph('The headline storage maxima select the faster read/write workload separately for bandwidth and IOPS. Read network performance assumes symmetry; only client-to-server OSU bandwidth was measured.', size=9)
    p.paragraph('The network IOPS proxy divides measured concurrent 4096-byte message bandwidth by 4096. It excludes request/reply, replication, protocol and DAOS costs. It is not a measured DAOS operation rate.', size=9)

    for metric, title, formatter in [('bandwidth_bytes_per_second', 'Per-node storage bandwidth', format_bw),
                                      ('iops', 'Per-node storage IOPS', format_iops)]:
        p.page(title)
        for workload in WORKLOADS:
            row = derived['storage']['per_node_statistics'][workload][metric]
            height = 88 + len(row['per_node'])*16
            if p.y-height < 55:
                p.page(title + ' (continued)')
            p.text(42, p.y, LABELS[workload], 12, True)
            p.y -= 19
            p.text(42, p.y, f"Mean {formatter(row['mean'])}   |   population stddev {formatter(row['stddev_population'])}", 9)
            p.y -= 16
            minimum = ', '.join(short_name(h, data) for h in row['min_nodes'])
            maximum = ', '.join(short_name(h, data) for h in row['max_nodes'])
            for line in textwrap.wrap(f"Min {formatter(row['min'])}: {minimum}   |   Max {formatter(row['max'])}: {maximum}", 110):
                p.text(42, p.y, line, 8)
                p.y -= 12
            p.y -= 5
            peak = row['max'] or 1
            for host, value in sorted(row['per_node'].items()):
                p.text(42, p.y, short_name(host, data), 9)
                p.rect(168, p.y-2, 270, 9, (.92, .94, .96))
                p.rect(168, p.y-2, 270*value/peak, 9, (.18, .45, .58))
                p.text(450, p.y, formatter(value), 9)
                p.y -= 16
            p.y -= 18
        p.paragraph('Statistics describe variation across storage nodes, not uncertainty across repeated runs. Random and sequential IOPS use different operation sizes and are shown separately.', size=9)

    p.page('Network diagnostics and interpretation')
    net = derived['network']
    p.kv('Peak network message size', f"{net['bandwidth_peak_message_bytes']:,} bytes")
    p.kv('Peak message rate', f"{net['maximum_message_rate_per_second']:,.0f} messages/s at {net['maximum_message_rate_message_bytes']:,} bytes (not storage IOPS)")
    p.kv('Unpaired clients / servers', f"{len(net['unpaired_clients'])} / {len(net['unpaired_servers'])}")
    for label, key, fmt in [('Pairwise peak bandwidth', 'pairwise_peak_bandwidth_statistics', format_bw),
                            ('Small-message latency', 'small_message_latency_statistics', lambda v: f'{v:.3f} us')]:
        row = net[key]
        if row:
            p.kv(label, f"Mean {fmt(row['mean'])}; stddev {fmt(row['stddev_population'])}")
            p.paragraph(f"Min {fmt(row['min'])}: {row['min_nodes'][0]}; max {fmt(row['max'])}: {row['max_nodes'][0]}", size=9)
    p.paragraph('Model and limitations', size=12)
    for item in derived['assumptions']:
        p.paragraph('- ' + item, size=9)
    if 'metadata' in derived.get('planes', {}):
        metadata = derived['planes']['metadata']
        p.page('Metadata-server component ceilings')
        p.paragraph('MDS devices and client-to-MDS OSU paths are measured separately from the data plane. Metadata operation comparisons assume one operation per I/O.', size=10)
        p.kv('Metadata servers', len(data['groups']['mds']))
        p.kv('MDS raw capacity', f"{metadata['capacity']['total_storage_bytes']/GIB:,.1f} GiB")
        for plane_name, plane in derived['planes'].items():
            p.kv(plane_name.title()+' bandwidth ceiling', format_bw(plane['cluster']['estimated_max_aggregate_bandwidth_bytes_per_second']))
            p.kv(plane_name.title()+' IOPS ceiling', format_iops(plane['cluster']['estimated_max_aggregate_iops_4KiB']))
        for direction, row in metadata['cluster']['by_direction'].items():
            p.kv('MDS '+direction+' storage bandwidth', format_bw(row['storage_bandwidth_bytes_per_second']))
            p.kv('MDS '+direction+' storage IOPS', format_iops(row['storage_iops_4KiB']))
            p.kv('Metadata '+direction+' bandwidth ceiling', format_bw(row['cluster_bandwidth']['value'])+' ('+row['cluster_bandwidth']['bottleneck']+')')
            p.kv('Metadata '+direction+' IOPS ceiling', format_iops(row['cluster_iops_4KiB']['value'])+' ('+row['cluster_iops_4KiB']['bottleneck']+')')
        p.kv('Client/MDS network bandwidth', format_bw(metadata['network']['estimated_max_aggregate_bandwidth_bytes_per_second']))
        p.kv('Client/MDS 4KiB message proxy', format_iops(metadata['network']['estimated_aggregate_iops_proxy_4KiB']))
        p.paragraph('Do not add these ceilings: clients and fabric are shared. Read ceilings assume the measured client-to-server bandwidth also holds in reverse.', size=9)
        p.page('Metadata-server storage balance')
        for workload, metrics in metadata['storage']['per_node_statistics'].items():
            p.paragraph(LABELS[workload], size=11)
            for metric, row in metrics.items():
                fmt = format_iops if metric == 'iops' else format_bw
                p.kv(metric, f"Mean {fmt(row['mean'])}; stddev {fmt(row['stddev_population'])}")
                p.paragraph(f"Min {fmt(row['min'])}: {', '.join(row['min_nodes'])}; max {fmt(row['max'])}: {', '.join(row['max_nodes'])}", size=9)
    return p.finish(), p.number



def generate(manifest_path, output_pdf, template):
    for tool in ('dot', 'ps2pdf'):
        if not shutil.which(tool):
            raise RuntimeError(f'Missing {tool}; install phase1 report prerequisites before phase7')
    data = json.loads(manifest_path.read_text())
    derived = derive(data)
    directory = manifest_path.parent / 'report'
    eps = render_topology(data, directory, template)
    postscript, pages = report_pages(data, derived, eps)
    generated = write_pdf(postscript, directory, 'performance-report', output_pdf)
    dot = directory / 'topology.dot'
    data['derived_performance'] = derived
    data['report'] = {'pdf': str(generated), 'workflow_pdf': str(output_pdf), 'pages': pages,
                      'topology_dot': str(dot), 'topology_png': str(directory / 'topology.png')}
    atomic_json(manifest_path, data)
    print(json.dumps({'manifest': str(manifest_path), 'pdf': str(generated),
                      'workflow_pdf': str(output_pdf), 'pages': pages, 'cluster': derived['cluster'],
                      'metadata_cluster': derived.get('planes', {}).get('metadata', {}).get('cluster')}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest')
    parser.add_argument('--output-pdf')
    parser.add_argument('--select', action='store_true')
    parser.add_argument('--root')
    parser.add_argument('--groups-json', default='{}')
    parser.add_argument('--pointer')
    parser.add_argument('--template', default=str(TOPOLOGY_TEMPLATE))
    args = parser.parse_args()
    if args.select:
        print(select_manifest(args.root, json.loads(args.groups_json), args.pointer))
        return
    if not args.manifest or not args.output_pdf:
        parser.error('--manifest and --output-pdf are required')
    generate(Path(args.manifest), Path(args.output_pdf), Path(args.template))


if __name__ == '__main__':
    main()

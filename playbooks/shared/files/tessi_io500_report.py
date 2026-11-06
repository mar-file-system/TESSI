#!/usr/bin/env python3
"""Saved IO500 filesystem results -> normalized manifest and shared PDF renderer.
No SSH, package installation, benchmarks, or writes to the baseline manifest.
Ansible supplies parsed YAML snapshots as JSON on stdin.
"""
import argparse
import configparser
import copy
import csv
import datetime
import hashlib
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import sys

PLAYBOOKS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLAYBOOKS / 'shared/files'))
from tessi_report_common import (GIB, Pages, stats, short_name, format_bw,
                                format_iops, atomic_json, render_topology, write_pdf)
_spec = importlib.util.spec_from_file_location('tessi_baseline_report', PLAYBOOKS / 'performance/files/report.py')
_baseline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_baseline)


def read_ini(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read(path)
    return parser


def numeric(value):
    found = re.match(r'\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)', str(value))
    return float(found[1]) if found else None


def read_response(path):
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    if 'stdout' in data:
        if data.get('rc', 0) or not data['stdout'].strip():
            return {'query_error': data.get('stderr', 'empty query output')}
        data = json.loads(data['stdout'])
    return data.get('response', data)


def select_run(root, pointer=None):
    root = Path(root).resolve()
    if pointer and Path(pointer).is_file():
        candidate = Path(Path(pointer).read_text().strip()).resolve()
        if candidate.is_relative_to(root) and (candidate / 'result.txt').is_file():
            return candidate
    candidates = []
    for result in (root / 'io500').glob('*/result.txt'):
        text = result.read_text(errors='replace')
        if '[SCORE]' in text:
            start = re.search(r'; START (.*)', text)
            candidates.append((start[1] if start else '', str(result.parent), result.parent))
    if not candidates:
        raise ValueError('No saved IO500 result.txt under this experiment; run phase6 or set io500_report_result_dir')
    return max(candidates)[2]


def counter_data(path):
    nodes = {}
    if not path.is_file():
        return nodes
    active = False
    host = None
    for line in path.read_text().splitlines():
        if line == 'PER-HOST DELTAS':
            active = True
        elif active and line and not line.startswith(' ') and line.endswith(':'):
            host = line[:-1]
            nodes[host] = {}
        elif active and host and line.startswith('  ') and ':' in line:
            key, value = line.strip().split(':', 1)
            value = value.strip()
            if value in ('True', 'False'):
                value = value == 'True'
            elif re.fullmatch(r'[-+]?\d+(?:\.\d+)?', value):
                value = float(value) if '.' in value else int(value)
            nodes[host][key] = value
    return nodes


def phase_results(run, config):
    result = read_ini(run / 'result.txt')
    text = (run / 'result.txt').read_text()
    phases = []
    for section in result.sections():
        if not section.startswith(('ior-', 'mdtest-', 'find')):
            continue
        family = section.rsplit('-', 1)[0]
        enabled = config.getboolean(section, 'run', fallback=config.getboolean(family, 'run', fallback=True))
        unit = 'GiB/s' if section.startswith('ior-') else 'kIOPS'
        score = numeric(result[section].get('score', ''))
        entry = {'name': section, 'enabled': enabled, 'score': score,
                 'score_unit': unit, 'seconds': numeric(result[section].get('t_delta', '')),
                 'rate': score * (GIB if unit == 'GiB/s' else 1000) if enabled and score is not None else None,
                 'rate_unit': 'bytes/second' if unit == 'GiB/s' else 'operations/second'}
        section_text = re.search(r'\[' + re.escape(section) + r'\]\n(.*?)(?=\n\[|\Z)', text, re.S)
        entry['validation_notes'] = re.findall(r'; ERROR (.*)', section_text[1]) if section_text else []
        entry['official_phase_valid'] = enabled and not entry['validation_notes']
        csv_path = run / (section + '.csv')
        entry['rank_statistics'] = None
        if enabled and csv_path.is_file() and section.startswith('mdtest-'):
            suffix = section.rsplit('-', 1)[-1]
            operation = {'write': 'creation', 'stat': 'stat', 'read': 'read', 'delete': 'removal'}[suffix]
            with csv_path.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            values = {row['rank']: float(row['rate-File ' + operation]) for row in rows
                      if row.get('rank', '').isdigit() and row.get('rate-File ' + operation)}
            entry['rank_statistics'] = stats(values)
        phases.append(entry)
    return result, phases


def saved_hosts(context, baseline, counters):
    hosts = {}
    saved = context.get('facts', {})
    versions = context.get('software_versions', {})
    for role in ('ds', 'clients', 'mds'):
        for host in context['groups'].get(role, []):
            fact = saved.get(host.split('.')[0], {})
            # Saved Ansible facts use unprefixed names, unlike live hostvars.
            fqdn = fact.get('fqdn', 'not recorded')
            detail = {'fqdn': fqdn, 'kernel': fact.get('kernel', 'not recorded'),
                      'os': fact.get('distribution', 'not recorded'),
                      'os_version': str(fact.get('distribution_version', 'not recorded')),
                      'ib_device': 'not recorded', 'ib_address': 'not recorded',
                      'software_versions': versions.get(host, []), 'role': role, 'fio': {}}
            iface = counters.get(host, {}).get('network_device')
            if not iface:
                iface = next((k for k, v in fact.items() if isinstance(v, dict) and v.get('type') == 'infiniband'), None)
            if iface:
                detail['ib_device'] = iface
                address = fact.get(iface, {}).get('ipv4', {})
                if address.get('address'):
                    prefix = ipaddress.IPv4Network('0.0.0.0/' + address.get('netmask', '255.255.255.255')).prefixlen
                    detail['ib_address'] = address['address'] + '/' + str(prefix)
            match = next((v for v in (baseline or {}).get('hosts', {}).values() if v.get('fqdn') == fqdn), None)
            if match and role in ('ds', 'mds'):
                detail['fio'] = {'devices': match.get('fio', {}).get('devices', [])}
            hosts[host] = detail
    return hosts


def scoped_baseline(data, hosts, groups):
    """Use measured endpoints only; never multiply an aggregate by a node ratio."""
    selected = {}
    matches = {}
    issues = []
    for role in ('ds', 'clients', 'mds'):
        selected[role] = []
        for current in groups.get(role, []):
            match = next((name for name in data['groups'].get(role, [])
                          if data['hosts'][name]['fqdn'] == hosts[current]['fqdn']), None)
            if not match:
                issues.append('No matching baseline ' + role + ' node for ' + current)
            else:
                selected[role].append(match)
                matches[current] = match
                if hosts[current]['kernel'] != data['hosts'][match]['kernel']:
                    issues.append('Kernel differs for ' + current)
    if len(matches) != len({host for role in ('ds', 'clients', 'mds') for host in groups.get(role, [])}):
        return None, matches, issues
    scoped = copy.deepcopy(data)
    scoped['groups'] = selected
    scoped['hosts'] = {name: data['hosts'][name] for role in selected for name in selected[role]}
    clients = {alias for name in selected['clients'] for alias in (name, data['hosts'][name]['fqdn'])}
    for role, network in [('ds', scoped['network']), ('mds', scoped['network'].get('metadata'))]:
        if not selected[role]:
            continue
        if not network:
            issues.append('No saved network baseline for ' + role)
            return None, matches, issues
        servers = {alias for name in selected[role] for alias in (name, data['hosts'][name]['fqdn'])}
        def cross(row):
            a, b = row['hosts']
            return (a in clients and b in servers) or (b in clients and a in servers)
        network['concurrent_pairs'] = [row for row in network['concurrent_pairs'] if cross(row)]
        network['pairwise'] = [row for row in network.get('pairwise', [])
                               if cross(row) or all(h in servers for h in row['hosts'])]
        used = {h for row in network['concurrent_pairs'] for h in row['hosts']}
        for label, names in [('clients', selected['clients']), ('servers', selected[role])]:
            network['unpaired_' + label] = [name for name in names if name not in used and data['hosts'][name]['fqdn'] not in used]
        if not network['concurrent_pairs']:
            issues.append('No measured concurrent pairs cover selected ' + role + ' endpoints')
            return None, matches, issues
    return _baseline.derive(scoped), matches, issues


def build_manifest(run, context, baseline_path=None):
    baseline = json.loads(baseline_path.read_text()) if baseline_path else None
    config = read_ini(run / 'config.ini')
    ini, phases = phase_results(run, config)
    counters = counter_data(run / 'network_storage_stats.txt')
    if (run / 'software_versions.json').is_file():
        context = dict(context, software_versions=json.loads((run / 'software_versions.json').read_text()))
    hosts = saved_hosts(context, baseline, counters)
    groups = {role: list(context['groups'].get(role, [])) for role in ('ds', 'clients', 'mds')}
    checks = {'node_kernel_issues': [], 'software_stack': 'not recorded in this run', 'stack_mismatches': []}
    derived = None
    matches = {}
    if baseline:
        derived, matches, checks['node_kernel_issues'] = scoped_baseline(baseline, hosts, groups)
        missing_versions = False
        for host, name in matches.items():
            current = hosts[host]['software_versions']
            reference = baseline['hosts'][name].get('software_versions', [])
            for package in ('doca', 'mpi', 'ucx'):
                pattern = {'doca': r'^doca-ofed(?:-|\s)',
                           'mpi': r'^(?:openmpi-\d|openmpi-bin(?::[^ ]+)?\s)',
                           'ucx': r'^(?:ucx-\d|libucx0(?::[^ ]+)?\s)'}[package]
                c = next((v for v in current if re.match(pattern, v)), None)
                b = next((v for v in reference if re.match(pattern, v)), None)
                if package == 'doca' and c is None and b is None:
                    continue
                if c is None or b is None:
                    missing_versions = True
                elif c != b:
                    checks['stack_mismatches'].append(host + ': ' + c + ' vs ' + b)
        if checks['stack_mismatches']:
            checks['software_stack'] = 'mismatch'
        elif matches and not missing_versions:
            checks['software_stack'] = 'match'
    mpi = json.loads((run / 'mpi-output.json').read_text()) if (run / 'mpi-output.json').is_file() else {}
    outside = sorted(set(context.get('facts', {})) - {h.split('.')[0] for h in hosts})
    if outside:
        checks['node_kernel_issues'].append('Saved nodes outside the report inventory: ' + ', '.join(outside))
    for phase in phases:
        comparison = {'fraction_of_component_estimate': None, 'reason': ''}
        if not phase['enabled']:
            comparison['reason'] = 'Phase disabled; zero is not measured performance'
        elif not derived:
            comparison['reason'] = 'No matching baseline estimate'
        elif phase['name'].startswith('mdtest-'):
            plane = derived['planes']['metadata'] if groups.get('mds') else derived
            denominator = plane['cluster']['estimated_max_aggregate_iops_4KiB']
            comparison['plane'] = 'metadata' if groups.get('mds') else 'data'
            comparison.update(
                component_estimate=denominator, metric='operations/second',
                fraction_of_component_estimate=phase['rate']/denominator
                    if phase['rate'] is not None and denominator else None,
                reason='Idealized comparison: one metadata operation equals one I/O; '
                       'uses the component-limited cluster IOPS estimate. '
                       'See node/kernel/software checks for baseline correspondence.')
        elif phase['name'] not in ('ior-easy-read', 'ior-easy-write', 'ior-rnd4K-easy-read'):
            comparison['reason'] = 'Different transfer size/access pattern; no like-for-like baseline'
        elif checks['node_kernel_issues'] or checks['software_stack'] == 'mismatch' or (context.get('system', {}).get('type', 'daos') == 'daos' and checks['software_stack'] != 'match'):
            comparison['reason'] = 'Inventory/kernel/stack correspondence is not fully verified'
        elif mpi.get('rc') != 0:
            comparison['reason'] = 'MPI did not complete successfully'
        elif any('Runtime is smaller than expected minimum runtime' not in note for note in phase['validation_notes']):
            comparison['reason'] = 'Phase validation errors require review'
        elif not phase['rate']:
            comparison['reason'] = 'No positive bandwidth result'
        else:
            direction = 'write' if phase['name'].endswith('write') else 'read'
            if phase['name'] == 'ior-rnd4K-easy-read':
                denominator = derived['cluster']['by_direction']['read']['cluster_iops_4KiB']['value']
                numerator = phase['rate'] / 4096
                comparison['metric'] = '4KiB operations/second'
            else:
                denominator = derived['cluster']['by_direction'][direction]['cluster_bandwidth']['value']
                numerator = phase['rate']
                comparison['metric'] = 'bytes/second'
            comparison.update(plane='data', component_estimate=denominator,
                              fraction_of_component_estimate=numerator/denominator if denominator else None,
                              reason='Engineering comparison before DAOS overhead; not an efficiency guarantee')
        phase['baseline_comparison'] = comparison
    pools = {}
    for name in ('before', 'after', 'after-cleanup'):
        response = read_response(run / ('space-' + name + '.json'))
        if response:
            pools[name] = response
    health = {name: read_response(run / ('system-' + name + '.json')) for name in ('before', 'after')}
    role_network = {}
    for role, names in groups.items():
        role_network[role] = {
            'available': all(h in counters and all(k in counters[h] for k in ('ib_hca_rx_bytes','ib_hca_tx_bytes')) for h in names),
            'rx_bytes': sum(counters.get(h, {}).get('ib_hca_rx_bytes', 0) for h in names),
            'tx_bytes': sum(counters.get(h, {}).get('ib_hca_tx_bytes', 0) for h in names),
            'rx_errors': sum(counters.get(h, {}).get('ib_hca_rx_errors', 0) for h in names),
            'tx_discards': sum(counters.get(h, {}).get('ib_hca_tx_discards', 0) for h in names),
            'traffic_statistics_bytes': stats({h: counters[h]['ib_hca_total_bytes'] for h in names
                                              if h in counters and 'ib_hca_total_bytes' in counters[h]})}
        balance = role_network[role]['traffic_statistics_bytes']
        role_network[role]['traffic_max_min_ratio'] = balance['max']/balance['min'] if balance and balance['min'] else None
    mpi = json.loads((run / 'mpi-output.json').read_text()) if (run / 'mpi-output.json').is_file() else {}
    errors = [line for line in mpi.get('stderr', '').splitlines() if 'ERROR' in line]
    cleanup_warnings = [line for line in errors if 'Failed to remove path' in line and ': 2:' in line]
    score = dict(ini['SCORE']) if ini.has_section('SCORE') else {}
    start = re.search(r'; START (.*)', (run / 'result.txt').read_text())
    ppn = re.search(r'[.]ppn-(\d+)[.]', ini.get('run', 'result-dir', fallback=''))
    sources = {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir()
               if p.is_file() and p.name in ('result.txt','config.ini','mpi-output.json','space-before.json','space-after.json','space-after-cleanup.json','software_versions.json')}
    return {'schema_version': 1, 'kind': context.get('system', {}).get('type', 'daos') + '-io500',
            'generated_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'run_directory': str(run), 'measured_start': start[1] if start else None,
            'groups': groups, 'hosts': hosts, 'system': context.get('system', {}),
            'topology_fabric_label': 'InfiniBand fabric\n' + context.get('system', {}).get('type', 'daos').upper() + ' data path',
            'io500': {'version': ini.get('run','version',fallback='unknown'),
                      'ranks': ini.getint('run','procs',fallback=0),
                      'configured_ranks_per_client': int(ppn[1]) if ppn else None,
                      'stonewall_seconds': config.getint('debug','stonewall-time',fallback=300),
                      'backend': config.get('global','api',fallback='unknown'),
                      'official_score_valid': '[INVALID]' not in (run/'result_summary.txt').read_text(),
                      'score': score, 'phases': phases, 'mpi_return_code': mpi.get('rc'),
                      'cleanup_missing_path_warnings': len(cleanup_warnings),
                      'other_error_lines': [line for line in errors if line not in cleanup_warnings]},
            'baseline': {'path': str(baseline_path) if baseline_path else None,
                         'sha256': hashlib.sha256(baseline_path.read_bytes()).hexdigest() if baseline_path else None,
                         'node_mapping': matches, 'checks': checks, 'scoped_estimates': derived},
            'health': health, 'pool_space': pools,
            'network': {'per_host': counters, 'by_role': role_network},
            'storage_counters': {'status': 'unavailable' if not counters or all(not v.get('storage_available') for v in counters.values()) else 'see source counters',
                                 'note': ('VFIO/SPDK I/O bypasses Linux block counters; unavailable is not zero I/O'
                                          if context.get('system', {}).get('type', 'daos') == 'daos' else
                                          'Linux device counters cover the saved test window and may include background I/O; unavailable is not zero I/O')},
            'provenance': {'source_sha256': sources, 'facts_source': 'saved IO500 facts snapshots'},
            'interpretation': ['Disabled phases have null measured rates.',
             'Short stonewall and disabled phases make this an engineering run, not a valid full IO500 submission.',
             'Metadata percentages assume one metadata operation equals one I/O against the component-limited cluster IOPS estimate.',
             'HCA RX and TX are separate endpoint counters; summing both endpoints double-counts traffic.',
             'Immediate post-cleanup pool snapshots do not establish completion of background reclamation.']}


def pages(data, eps):
    system_type = data['system'].get('type', 'daos')
    label = 'DAOS-' + data['system'].get('access', 'api').upper() if system_type == 'daos' else system_type.upper()
    p = Pages(default_subtitle='TESSI / ' + label, footer='Saved IO500 results | ' + label + ' / baseline comparison')
    io = data['io500']; base = data['baseline']; derived = base['scoped_estimates']
    p.page(label + ' performance report', 'TESSI / SYSTEM PERFORMANCE')
    p.paragraph(f"{len(data['groups']['ds'])} data servers / {len(data['groups'].get('mds', []))} metadata servers / {len(data['groups']['clients'])} clients / {io['ranks']} MPI ranks",size=12)
    p.paragraph('IO500 start: ' + str(data['measured_start']), size=9)
    p.embed_eps(eps, 32, 170, 548, 450)
    p.text(42,145,'Logical fabric view; SSD counts come from the matched baseline, not live device queries.',9)
    p.text(42,126,'Direct DAOS DFS API; no dfuse mount.' if io['backend'].startswith('DFS') else 'Filesystem I/O backend: '+io['backend'],9)
    p.text(42,100,'Engineering run' if not io['official_score_valid'] else 'Full IO500 result',12,True)
    p.text(42,81,'Baseline checks and phase validity are documented on the following pages.',9)

    p.page('System and run scope')
    hosts=list(data['hosts'].values())
    for key,value in [
      ('IO500 version',io['version']),(label+' configured version',str(data['system'].get('version','not recorded'))+' / '+str(data['system'].get('access','api'))),
      ('Kernel',', '.join(sorted({h['kernel'] for h in hosts}))),
      ('OS',', '.join(sorted({h['os']+' '+h['os_version'] for h in hosts}))),
      ('MPI rank count',io['ranks']),('Ranks per client (configured)',io['configured_ranks_per_client'] or 'not recorded'),('Stonewall',str(io['stonewall_seconds'])+' seconds'),
      ('Backend',io['backend']),('MPI exit status',io['mpi_return_code']),
      ('Official IO500 score','Valid' if io['official_score_valid'] else 'INVALID - shortened and/or partial test suite'),
      ('Enabled phases',', '.join(r['name'] for r in io['phases'] if r['enabled'])),
      ('Disabled phases',', '.join(r['name'] for r in io['phases'] if not r['enabled'])),
      ('Baseline stack check',base['checks']['software_stack'])]:
        p.kv(key,value)
    if system_type == 'pnfs':
        for key in ('ds_transport', 'client_mds_assignment', 'stripe_width', 'stripe_size', 'mds_threads', 'hpc_serve_layouts', 'pnfs_colocated', 'pnfs_ds_devices', 'pnfs_mds_devices', 'pnfs_mds_port'):
            p.kv(key, data['system'].get(key, 'not recorded'))
        p.paragraph('Configuration above comes from the report inventory; node identities and measurements come from saved run files.',size=9)
    p.paragraph('Source: '+data['run_directory'],size=8)

    p.page(label + ' phase measurements')
    p.paragraph('Rates are cluster-wide. Disabled phases are unavailable, not zero. Consult the configured stonewall and phase validity; shortened runs are engineering measurements.',size=10)
    y=p.y
    for x,label in [(42,'Phase'),(230,'Rate'),(345,'Time'),(400,'Validity'),(465,'% of theoretical max')]: p.text(x,y,label,8,True)
    p.y-=22
    for row in io['phases']:
        if p.y < 95:p.page(label + ' phase measurements (continued)')
        value='disabled' if not row['enabled'] else format_bw(row['rate']) if row['rate_unit']=='bytes/second' else format_iops(row['rate'])
        p.text(42,p.y,row['name'],9);p.text(230,p.y,value,9)
        p.text(345,p.y,f"{row['seconds'] or 0:.1f}s" if row['enabled'] else '-',9)
        p.text(400,p.y,'valid' if row['official_phase_valid'] else 'disabled' if not row['enabled'] else 'invalid',9)
        fraction = row['baseline_comparison']['fraction_of_component_estimate']
        p.text(475,p.y,f'{100*fraction:.1f}%' if fraction is not None else 'N/A',9)
        p.y-=23
    p.y-=12
    p.paragraph('Metadata percentages assume one metadata operation equals one I/O. The denominator is the MDS ceiling for split metadata, otherwise the shared-server ceiling: min(storage, network). N/A means disabled or no comparable baseline.',size=9)
    p.kv('Metadata composite', str(io['score'].get('md','unavailable'))+' kIOPS (geometric score; not a sum)')
    p.kv('Official total score', io['score'].get('score','unavailable'))
    p.kv('Missing-path cleanup warnings',io['cleanup_missing_path_warnings'])
    p.paragraph('These warnings concern removal of paths that do not exist; they are kept separately from other errors. Disabled IOR phases may leave no files to remove.',size=9)
    if io['other_error_lines']: p.paragraph('Other errors: '+'; '.join(io['other_error_lines'][:4]),size=9)

    p.page('Comparison with component baseline')
    p.paragraph('Baseline: '+str(base['path']),size=8)
    p.kv('Matched physical nodes',str(len(base['node_mapping']))+' / '+str(len(data['hosts'])))
    p.kv('Kernel / identity issues','; '.join(base['checks']['node_kernel_issues']) or 'none recorded')
    p.kv('Software version comparison',base['checks']['software_stack'])
    if derived:
        p.kv('Storage read / write',format_bw(derived['storage']['aggregate_by_workload']['read']['bandwidth_bytes_per_second'])+' / '+format_bw(derived['storage']['aggregate_by_workload']['write']['bandwidth_bytes_per_second']))
        p.kv('Raw random read / write',format_iops(derived['storage']['aggregate_by_workload']['randread']['iops'])+' / '+format_iops(derived['storage']['aggregate_by_workload']['randwrite']['iops']))
        p.kv('Cluster bandwidth estimate',format_bw(derived['cluster']['estimated_max_aggregate_bandwidth_bytes_per_second']))
        p.kv('4KiB message-rate proxy',format_iops(derived['cluster']['estimated_max_aggregate_iops_4KiB']))
        p.kv('Estimate bottlenecks',derived['cluster']['bandwidth_bottleneck']+' bandwidth; '+derived['cluster']['iops_bottleneck']+' IOPS proxy')
    if derived and data['groups'].get('mds'):
        meta = derived['planes']['metadata']
        p.kv('Metadata IOPS estimate', format_iops(meta['cluster']['estimated_max_aggregate_iops_4KiB']))
        p.kv('Metadata IOPS bottleneck', meta['cluster']['iops_bottleneck'])
        p.paragraph('IOR uses the DS data plane; mdtest uses the MDS metadata plane. These isolated ceilings share client NICs and fabric and must not be added.',size=9)
    if base['checks']['software_stack'] != 'match':
        p.paragraph('Package correspondence is unverified or mismatched; review checks before interpreting percentages.',size=9)
    p.paragraph('Comparison rules',size=12)
    for row in io['phases']:
        if row['enabled'] and row['name'].startswith('ior-'):
            c=row['baseline_comparison']
            p.kv(row['name'],f"{100*c['fraction_of_component_estimate']:.1f}% of component estimate" if c['fraction_of_component_estimate'] is not None else c['reason'])
    if not any(r['enabled'] and r['name'].startswith('ior-') for r in io['phases']):
        p.paragraph('No bandwidth comparison is available: all IOR phases were disabled.')
    p.paragraph('Metadata percentages use an idealized one-operation-per-I/O assumption against the cluster IOPS estimate. Real metadata operations can require multiple storage or network operations. Percentages are reference comparisons, not measured hardware efficiency; baseline correspondence checks above still apply.',size=10)
    p.paragraph('The baseline is scoped to measured participating endpoints. It never includes client disks or scales an aggregate by the client/server count ratio. Unpaired links are not extrapolated.',size=9)

    p.page('Metadata balance across MPI ranks')
    p.paragraph('CSV rates describe client MPI ranks, not storage-server IOPS. They show imbalance within each phase; the headline rate remains IO500\'s cluster result.',size=10)
    for row in io['phases']:
        s=row['rank_statistics']
        if not row['enabled'] or not s:continue
        if p.y<145:p.page('MPI rank balance (continued)')
        p.text(42,p.y,row['name'],12,True);p.y-=21
        p.paragraph(f"Ranks: {s['count']} | mean {s['mean']:,.0f} ops/s | population stddev {s['stddev_population']:,.0f} ops/s",size=9)
        p.paragraph(f"Min rank(s) {', '.join(s['min_nodes'])}: {s['min']:,.0f} ops/s; max rank(s) {', '.join(s['max_nodes'])}: {s['max']:,.0f} ops/s",size=9)

    p.page('Network balance by node role')
    p.paragraph('Native IB HCA counters include RDMA. IPoIB counters alone miss verbs traffic. Byte counts cover the full test window; they are not peak bandwidth measurements.',size=10)
    for role,row in data['network']['by_role'].items():
        if not row['available']:
            p.kv(role+' counters','not recorded for every participating node')
            continue
        p.kv(role+' RX / TX',f"{row['rx_bytes']/GIB:.3f} / {row['tx_bytes']/GIB:.3f} GiB")
        p.kv(role+' errors / discards',str(row['rx_errors'])+' / '+str(row['tx_discards']))
        s=row['traffic_statistics_bytes']
        if s:
            if p.y < 150+len(s['per_node'])*18:p.page('Network balance (continued)')
            p.paragraph(f"Within-role max/min traffic ratio: {row['traffic_max_min_ratio']:.6f}" if s['min'] else 'Within-role traffic ratio unavailable',size=9)
            for host,value in sorted(s['per_node'].items()):
                p.text(42,p.y,short_name(host,data),9)
                p.rect(170,p.y-2,260*value/(s['max'] or 1),9,(.18,.45,.58))
                p.text(445,p.y,f'{value/GIB:.3f} GiB',9);p.y-=19
            p.y-=20
    p.paragraph('Client/server traffic totals differ because the roles do different work. Endpoint RX+TX sums are not logical payload bytes or replication factors.',size=9)
    p.kv('Linux block counters',data['storage_counters']['status'])
    p.paragraph(data['storage_counters']['note'],size=9)

    if system_type == 'daos':
        p.page('Pool capacity, cleanup and engine health')
        for stage,response in data['health'].items():
            members=(response or {}).get('members',[])
            p.kv('Engines '+stage,', '.join(str(m.get('rank'))+': '+m.get('state','unknown') for m in members) or 'not recorded')
        for stage,response in data['pool_space'].items():
            p.paragraph(stage.replace('-',' ').capitalize(),size=12)
            p.kv('Pool state / targets',str(response.get('state','unknown'))+' / '+str(response.get('active_targets','?'))+' active, '+str(response.get('disabled_targets','?'))+' disabled')
            for tier in response.get('tier_stats',[]):
                p.kv(tier['media_type']+' free / total',f"{tier['free']/GIB:.3f} / {tier['total']/GIB:.3f} GiB")
        p.paragraph('Raw physical capacity from the component baseline is not the configured pool size. Immediate cleanup snapshots may precede background reclamation; retained bytes alone do not prove a leak.',size=9)
    else:
        p.page('Run provenance and limitations')
        p.paragraph('Filesystem free-space and pNFS service-health snapshots were not archived by this run; the report does not infer them from raw device capacity.',size=9)
    p.paragraph('Report provenance',size=12)
    p.paragraph('All charts use saved result files and facts. The baseline is read-only. The results manifest stores phase scope/validity, source hashes, node mapping, scoped estimates, rank statistics and diagnostic snapshots.',size=9)
    p.paragraph('Run-to-run variance is unknown: this report describes one run. Population standard deviations show rank or node spread, not confidence intervals.',size=9)
    return p.finish(),p.number


def generate(run, context, baseline_path, output_pdf):
    data=build_manifest(run,context,baseline_path)
    directory=run/'report'
    eps=render_topology(data,directory)
    postscript,count=pages(data,eps)
    system_type=context.get('system', {}).get('type', 'daos')
    pdf=write_pdf(postscript,directory,system_type+'-report',output_pdf)
    manifest=run/(system_type+'_manifest.json')
    data['report']={'pdf':str(pdf),'workflow_pdf':str(output_pdf),'pages':count}
    atomic_json(manifest,data)
    print(json.dumps({'pdf':str(pdf),'manifest':str(manifest),'baseline':str(baseline_path) if baseline_path else None,
                      'workflow_pdf':str(output_pdf),'pages':count,'official_io500_valid':data['io500']['official_score_valid']},indent=2))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--select',action='store_true');parser.add_argument('--result-root');parser.add_argument('--pointer')
    parser.add_argument('--run');parser.add_argument('--baseline');parser.add_argument('--output-pdf')
    args=parser.parse_args()
    if args.select:
        print(select_run(args.result_root,args.pointer));return
    if not args.run or not args.output_pdf:parser.error('--run and --output-pdf are required')
    generate(Path(args.run),json.load(sys.stdin),Path(args.baseline) if args.baseline else None,Path(args.output_pdf))


if __name__=='__main__':main()

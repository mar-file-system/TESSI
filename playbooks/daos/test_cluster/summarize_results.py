"""Summarize a completed native DAOS MPI sweep without running any I/O."""
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
clients = int(sys.argv[2])
rows = []
for path in root.glob('ppn-*.bytes-*/metrics.json'):
    ppn = int(path.parent.name.split('.')[0].removeprefix('ppn-'))
    metrics = json.loads(path.read_text())
    validation = json.loads((path.parent / 'validation.jsonl').read_text())
    assert validation['validation'] == 'PASS', f'Validation failed: {path.parent}'
    assert {m['operation'] for m in metrics} == {'write', 'read'}, f'Incomplete metrics: {path}'
    for m in metrics:
        assert m['ranks'] == clients * ppn, f'Unexpected rank count: {path}'
        rows.append(dict(m, clients=clients, ranks_per_client=ppn))
assert rows, 'No completed MPI metrics found'
rows.sort(key=lambda m: (m['ranks_per_client'], m['value_bytes'], m['operation'] != 'write'))
lines = [f'DAOS-API MPI: {clients} clients; {len(rows) // 2} completed cases',
         'Ranks/client  Ranks  Value bytes  Operation    Cluster IOPS    Cluster MiB/s']
for m in rows:
    lines.append(f"{m['ranks_per_client']:12d}  {m['ranks']:5d}  {m['value_bytes']:11d}  "
                 f"{m['operation']:9s}  {m['cluster_iops']:14,.1f}  {m['cluster_bandwidth_MiBps']:15,.1f}")
lines.append('Logical KV operations/payload; replication traffic excluded. Cross-rank verification passed.')
text = '\n'.join(lines) + '\n'
(root / 'performance-summary.txt').write_text(text)
(root / 'performance-summary.json').write_text(json.dumps(rows, indent=2) + '\n')
print(text, end='')

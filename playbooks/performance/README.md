# Xem component performance baseline

From the shared TESSI checkout on an allocated client:

```sh
./bootstrap.sh --make all configs/xem/performance.yaml
```

This uses the DAOS allocation aliases `ds[0:3].daos-$USER.mvpnet` and
`cli[0:3].daos-$USER.mvpnet`. Edit the inventory for a different allocation.
Run on a fresh allocation **before DAOS binds or initializes its SSDs**.
FIO overwrites the explicitly listed whole NVMe devices. Mounted devices,
partitions, filesystem signatures, active swap and a running DAOS server are
rejected; this workflow does not wipe signatures or unbind VFIO devices.

Phase1 installs FIO, OSU and the same pinned DOCA-OFED 3.2.1 / UCX 1.20 /
Open MPI stack used by DAOS through `shared/install_doca.yaml`. There is no
distro MPI fallback. The common DNF transaction replaces conflicting distro
RDMA packages without manually erasing the active stack beforehand.

Run phase1 from an allocated client: the common controller guard rejects a
storage-server controller. Storage boot preparation is shared with DAOS: it
enables IOMMU, keeps the running kernel as the boot default, and reboots storage
servers when IOMMU or newly installed OFED drivers require it. Xem IB addressing
is restored afterward. This does not bind, format or initialize the SSDs.
OSU is rebuilt when its MPI runtime/compiler identity changes, so an old distro
build is not reused after switching to DOCA. Phase5 checks SSH and IB; phase6
measures the system. No installation occurs in phase6 or phase7.

For an existing performance Makefile, run `make phase1-clean all` from the client
to install the shared stack and collect a new baseline. Old manifests are retained
but still describe the old software stack; use the new manifest for DAOS.
The final phase7 debug message prints its absolute path and a ready-to-copy
`performance_manifest: ...` entry for `configs/xem/daos.yaml`.

Tunable settings are under `system.performance` in the config. FIO runs one
job per device and launches all servers concurrently: 1MiB sequential write
and read, then 4KiB random write and read. Tests use a 32GiB region per SSD,
60 seconds plus 5 seconds ramp per workload. These quick baselines are not a
full-device steady-state SSD endurance/preconditioning study.

OSU measures latency and bandwidth for every client/server pair and every
server/server pair, then launches node-disjoint client/server bandwidth pairs
concurrently. This supports arbitrary positive client/server counts; unmatched
nodes are recorded. Phase1 and the phase6 preflight verify that UCX exposes an rc transport.
Network tests require Open MPI UCX/RDMA; there is no TCP
fallback. The concurrent-pair aggregate is an approximate overlapping-sweep
measurement, not a synchronized all-to-all network capacity test.

Results are under:

```
/proj/mvpnet/$USER/experiments/performance/
  <kernel>-<OS>-<version>-4-clients-4-ds-8-physical_hosts/
    <timestamp>-<unique suffix>/
      manifest.json
      summary.txt
      raw/<inventory hostname>/<benchmark output>
```

Mixed OS/kernel versions are represented in the identity. Actual physical
hostnames, CPU/memory, SSD model/serial/capacity, IB addresses, relevant package
versions, commands, configuration and individual measurements are retained.
The manifest embeds raw results as well as storing separate raw files.
A concise storage aggregate and concurrent network aggregate are printed.

The manifest is intended for a later optional DAOS report input. Raw 4KiB
block IOPS do not predict mdtest metadata IOPS directly, and summed component
bandwidth does not account for DAOS replication/protocol overhead. Verify the
recorded kernel, hosts, devices and RDMA/MPI versions when reusing a baseline.
Phase6 runs tests and saves measurements; phase7 builds the generic PDF report.
To iterate on reporting without rerunning benchmarks, use `make phase7-clean phase7`.
`make all` stops at phase7. Explicit `make phase8` updates the main
`compatibility.yaml` after phase7 succeeds. The DAOS phase7 adapter consumes the pinned baseline for role-aware comparisons.

## Shared implementation

The performance workflow reuses TESSI's pinned DOCA stack installer, RPM Open MPI discovery
and module registration, MPI environment loader, MPI executable discovery,
hostfile writer, OSU installer and OSU path resolver. `tasks/build_mpi_command.yaml`
provides common launch settings to performance OSU, shared OSU, IO500, IOR and
native DAOS tests, including the full-hostname option required by Xem.
The Python baseline runner receives the launcher as an argv list; it does not
maintain its own MPI prefix, SSH flags or OSU installation prefix.
The existing filesystem FIO runner cannot operate on raw SSDs, so raw-device
validation, device workload scheduling and manifest aggregation remain here.

## Phase7 PDF and derived measurements

Run `make phase7-clean phase7` in the generated Makefile directory to regenerate
reports without rerunning tests. The performance-specific report reads saved
measurements only and uses the existing Graphviz/Ghostscript toolchain; it does
not install packages. DAOS uses its own adapter with the same renderer; other systems keep the generic phase7 report.

The PDF is saved as `<baseline run>/report/performance-report.pdf` and copied to
`<artifacts>/images/summary.pdf`. The same report folder contains the editable
DOT source, topology PNG/EPS and PostScript source.

New phase6 runs save their exact manifest path in
`<artifacts>/images/performance-manifest-path.txt`. For runs made before that
pointer existed, phase7 selects the newest completed baseline with matching
storage/client inventory, using the original measurement timestamp (not the
manifest modification time). To select another run explicitly, pass
`-e performance_manifest_path=/absolute/path/to/manifest.json` to the phase7
Ansible playbook.

All calculated values are added atomically under `derived_performance` in the
original performance manifest, preserving the raw samples and measurement timestamp:

- `capacity`: total/per-node raw bytes and device count.
- `storage.aggregate_by_workload`: node sums for each sequential/random
  read/write workload; bandwidth is bytes/s and IOPS is operations/s.
- `storage.per_node_statistics`: mean, population standard deviation, min/max,
  all tied node identities, coefficient of variation and each node's value.
- `network.aggregate_curve`: concurrent-pair summed bandwidth and message rate
  for every common message size, with peak bandwidth and pairwise diagnostics.
- `network.estimated_aggregate_iops_proxy_4KiB`: concurrent OSU bandwidth at
  exactly 4096 bytes divided by 4096; absent samples produce null, not a guess.
- `cluster`: minimum of storage and network estimates, including read/write
  estimates and the limiting component.
- `method`, `units`, `assumptions`, `environment`, and `calculated_at_utc` describe
  how to interpret the values; `report` records output paths and page count.

The headline storage bandwidth selects the faster aggregate sequential
read/write result; headline storage IOPS selects the faster aggregate random
4KiB read/write result. Network bandwidth is the maximum concurrent-pair sum
at a common message size, converting OSU decimal MB/s to bytes/s. The report
also retains separate directional storage results. Only client-to-server
network bandwidth was measured, so read estimates assume symmetry.

These are empirical component-limited estimates, not proven hardware limits.
A one-way 4KiB message is only a proxy for an I/O operation: request/reply,
replication, protocol and DAOS costs are excluded. Independent concurrent OSU
sweeps were not barrier-synchronized. Raw FIO IOPS cannot directly predict
mdtest metadata IOPS. Population standard deviations describe variation among
nodes; the baseline contains no repeated runs to estimate temporal uncertainty.

Report layout, units, statistics, Graphviz rendering and PDF output are shared
with DAOS through `shared/files/tessi_report_common.py` and
`shared/templates/report_topology.dot.j2`. DAOS writes a separate results
manifest and does not modify the performance baseline.

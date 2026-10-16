# DAOS-API on Xem

The `configs/xem/daos.yaml` inventory selects `system.type: daos` and
`system.access: api`. Bootstrap may run on any controller. Phase1 must run
from an allocated client, because it automatically reboots storage servers
when IOMMU groups are missing. Its controller guard is covered by
`tests/ansible/test_daos_controller.yaml`.

Run from the shared TESSI checkout on cli0:

```sh
ansible-playbook -i configs/xem/daos.yaml playbooks/bootstrap/bootstrap.yaml
# Use the Makefile path printed by bootstrap:
make -f /path/to/artifacts/Makefile VERBOSE=1 phase1 phase5 phase6
```

Bootstrap creates the generated Makefile and inventories on all physical
nodes. Phase status markers belong to the node running make. Phase1 retains
the running kernel when regenerating Xem's static GRUB menu, performs any
required server reboots within Ansible, verifies active IOMMU groups, and
restores IPoIB through a persistent boot service before succeeding.

Phase5 reuses the shared firewall, SSH, and InfiniBand discovery tasks. It
configures one five-target UCX engine per storage server, using five explicit
NVMe devices with metadata on SSD, 32 GiB RAM-backed SCM, and persistent
control metadata in `/var/lib/daos`. The first three servers host management
replicas. Control endpoints use gathered management IPv4 addresses. Client
agents provide authentication and attach information. Transport certificates
are disabled for this isolated testbed allocation.

Storage devices with partitions, mounts, or filesystem signatures are
rejected before binding to VFIO. PCI mappings are saved for reruns, and an
initialized server configuration fingerprint prevents accidental topology
changes. Initial formatting is skipped once the system is queryable.
Existing pools and containers are reused. The default 1 TB pool is `tessi`,
and its generic native-API container is `api`. No filesystem mount is created.

Phase1 registers DOCA's existing Open MPI with TESSI's shared module installer and compiles
`daos_api_mpi.c`. Phase6 uses the shared hostfile and module launch tasks
and installs no packages or executables. No separate MPI packages are installed;
DOCA already supplies the compiler wrapper, headers, and libraries. All
inventory clients participate, including a one-client inventory. By default
it sweeps 1, 4, and 16 ranks per client with 4 KiB and 1 MiB values. Each case
measures 30 seconds of writes followed by 30 seconds of reads, with MPI
barriers between stages. Each rank issues synchronous native KV operations;
many ranks provide concurrent outstanding requests across the cluster.

The test seeds 128 keys per rank before timing, then measures overwrites and
reads of that bounded working set. Cluster IOPS equals summed successful KV
calls divided by the slowest rank's elapsed time. Bandwidth equals logical
payload bytes divided by the same time (both B/s and MiB/s); replication
traffic is excluded. Every rank verifies the next rank's entire working set
byte for byte outside the timed region. This workload attempts saturation
through the concurrency sweep; it does not prove maximum hardware throughput
or measure cold reads. All engines must remain joined before and after.

Under `system.daos`, override `api_ranks_per_client` (list), `api_value_sizes`
(list of bytes), `api_seconds`, `api_slots`, and `api_timeout` (default 600
seconds per MPI case). Rank counts must fit every client's CPU count. The
six default cases take at least six minutes plus setup and validation.

Results are printed in Ansible output and stored in
`result_dir/daos_api/<run-id>/ppn-<ranks>.bytes-<size>/`: `metrics.json`
contains aggregate read/write rates, `validation.jsonl` records successful
cross-rank checking, and `output.json` preserves MPI stdout/stderr even on
failure. The parent directory contains engine state and `summary.txt`.
Each case creates a uniquely labeled temporary container and deletes it in
an Ansible always block after success or failure. Result files are retained.
Previously retained objects in the shared api container are not deleted.
DAOS reclaims deleted storage asynchronously; target-level space pressure
can still require separate investigation. No dfuse, POSIX data I/O, or IO500 is used.
`phase5-clean` stops services without deleting data.

Server options can be overridden under `system.daos`: `provider`, `targets`,
`scm_size`, `pool`, `pool_size`, `container`, and `group`. Bootstrap preserves
this namespace in generated inventories. The default provider is `ucx+rc_x`.

Run the controller-placement regression test without installing or rebooting:

```sh
ansible-playbook -i localhost, -c local tests/ansible/test_daos_controller.yaml
```

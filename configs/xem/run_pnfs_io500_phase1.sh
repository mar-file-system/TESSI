#!/usr/bin/env bash
set -euo pipefail

tessi_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
config_dir="$tessi_dir/configs/xem/pnfs_io500_phase1"
artifact_root="/tmp/${USER}/experiments"
cd "$tessi_dir"

configs=(
  transport-rdma_striping-on_ppn-8.yaml
  transport-rdma_striping-on_ppn-16.yaml
  transport-rdma_striping-on_ppn-32.yaml
  transport-rdma_striping-off_ppn-1.yaml
  transport-rdma_striping-off_ppn-8.yaml
  transport-rdma_striping-off_ppn-16.yaml
  transport-rdma_striping-off_ppn-32.yaml
  transport-tcp_striping-on_ppn-1.yaml
  transport-tcp_striping-on_ppn-8.yaml
  transport-tcp_striping-on_ppn-16.yaml
  transport-tcp_striping-on_ppn-32.yaml
)

initial_config="$config_dir/transport-rdma_striping-on_ppn-1.yaml"
initial_hash=$(sha256sum "$initial_config" | cut -c1-8)
current_artifact="$artifact_root/$initial_hash/pmanual/artifacts"

for config_name in "${configs[@]}"; do
  config_path="$config_dir/$config_name"

  if [[ -e "$current_artifact/status/status.phase5" ]]; then
    echo ">>> Cleaning the previous deployment: $current_artifact"
    make -C "$current_artifact" phase5-clean FORCE=1
  else
    echo ">>> Previous deployment is already clean: $current_artifact"
  fi

  echo ">>> Bootstrapping Phase 1 config: $config_path"
  "$tessi_dir/bootstrap.sh" "$config_path"

  config_hash=$(sha256sum "$config_path" | cut -c1-8)
  current_artifact="$artifact_root/$config_hash/pmanual/artifacts"
  test -f "$current_artifact/Makefile"

  echo ">>> Reusing prepared hardware phases 0-4 for hash $config_hash"
  make -C "$current_artifact" -t phase4
  printf '%s\n' \
    "Phase 1 screening reused invariant hardware preparation via: make -t phase4" \
    "Configuration: $config_path" \
    > "$current_artifact/logs/phase0-4-reuse.txt"

  echo ">>> Running Phase 1 config: $config_name (hash $config_hash)"
  make -C "$current_artifact" all
done

echo ">>> Phase 1 screening matrix completed"

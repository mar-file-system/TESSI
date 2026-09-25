#!/usr/bin/env bash
set -euo pipefail

tessi_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
config_dir="$tessi_dir/configs/xem/pnfs_io500_phase1"
artifact_root="/tmp/${USER}/experiments"
cd "$tessi_dir"

configs=(
  transport-rdma_striping-on_ppn-16_mds-round-robin.yaml
  transport-rdma_striping-off_ppn-16_mds-round-robin.yaml
)

cleanup_active_deployment() {
  local status_file
  local artifact_dir
  local -a active_status_files

  mapfile -t active_status_files < <(
    find "$artifact_root" -path '*/pmanual/artifacts/status/status.phase5' -type f
  )
  if (( ${#active_status_files[@]} == 0 )); then
    return 0
  fi
  if (( ${#active_status_files[@]} > 1 )); then
    echo "ERROR: found multiple active Phase 5 deployments:" >&2
    printf '  %s\n' "${active_status_files[@]}" >&2
    return 1
  fi

  status_file=${active_status_files[0]}
  artifact_dir=${status_file%/status/status.phase5}
  echo ">>> Cleaning the active deployment: $artifact_dir"
  make -C "$artifact_dir" phase5-clean FORCE=1
}

"$tessi_dir/configs/xem/generate_pnfs_io500_phase1.py"

for config_name in "${configs[@]}"; do
  cleanup_active_deployment
  config_path="$config_dir/$config_name"

  echo ">>> Bootstrapping Phase 1 config: $config_path"
  "$tessi_dir/bootstrap.sh" "$config_path"

  config_hash=$(sha256sum "$config_path" | cut -c1-8)
  artifact_dir="$artifact_root/$config_hash/pmanual/artifacts"
  test -f "$artifact_dir/Makefile"

  echo ">>> Reusing prepared hardware phases 0-4 for hash $config_hash"
  make -C "$artifact_dir" -t phase4
  printf '%s\n' \
    "Round-robin screening reused invariant hardware preparation via: make -t phase4" \
    "Configuration: $config_path" \
    > "$artifact_dir/logs/phase0-4-reuse.txt"

  echo ">>> Running Phase 1 config: $config_name (hash $config_hash)"
  make -C "$artifact_dir" all
done

echo ">>> Round-robin Phase 1 comparison completed"

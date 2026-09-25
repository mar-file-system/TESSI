#!/usr/bin/env bash
set -uo pipefail

tessi_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
config_dir="$tessi_dir/configs/xem/pnfs_io500_scaling"
artifact_root="/tmp/${USER}/experiments"
cd "$tessi_dir"

# Diagnostic points around the failed 1/2/2 run, followed by independent
# client-count and DS-count sweeps.  Existing completed points are not rerun.
configs=(
  mds-1_ds-1_clients-2.yaml
  mds-1_ds-2_clients-1.yaml
  mds-2_ds-2_clients-2.yaml
  mds-4_ds-10_clients-1.yaml
  mds-4_ds-10_clients-2.yaml
  mds-4_ds-10_clients-4.yaml
  mds-4_ds-10_clients-8.yaml
  mds-4_ds-1_clients-10.yaml
  mds-4_ds-2_clients-10.yaml
  mds-4_ds-4_clients-10.yaml
  mds-4_ds-8_clients-10.yaml
)

failures=()

cleanup_active_deployment() {
  local status_file
  local artifact_dir
  local -a active_status_files

  mapfile -t active_status_files < <(
    find "$artifact_root" -path '*/pmanual/artifacts/status/status.phase5' -type f
  )

  if (( ${#active_status_files[@]} == 0 )); then
    echo ">>> No active Phase 5 deployment found"
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

"$tessi_dir/configs/xem/generate_pnfs_io500_scaling.py"

for config_name in "${configs[@]}"; do
  config_path="$config_dir/$config_name"

  if ! cleanup_active_deployment; then
    echo "ERROR: cannot safely continue to $config_name" >&2
    exit 1
  fi

  echo ">>> Bootstrapping scaling config: $config_path"
  if ! "$tessi_dir/bootstrap.sh" "$config_path"; then
    failures+=("$config_name (bootstrap)")
    continue
  fi

  config_hash=$(sha256sum "$config_path" | cut -c1-8)
  artifact_dir="$artifact_root/$config_hash/pmanual/artifacts"
  if [[ ! -f "$artifact_dir/Makefile" ]]; then
    failures+=("$config_name (missing Makefile)")
    continue
  fi

  echo ">>> Reusing prepared hardware phases 0-4 for hash $config_hash"
  if ! make -C "$artifact_dir" -t phase4; then
    failures+=("$config_name (reuse phases 0-4)")
    continue
  fi
  printf '%s\n' \
    "Scaling study reused invariant hardware preparation via: make -t phase4" \
    "Configuration: $config_path" \
    > "$artifact_dir/logs/phase0-4-reuse.txt"

  echo ">>> Running scaling config: $config_name (hash $config_hash)"
  if ! make -C "$artifact_dir" all; then
    failures+=("$config_name (make all)")
  fi
done

cleanup_active_deployment || failures+=("final cleanup")

if (( ${#failures[@]} > 0 )); then
  echo ">>> Scaling sweep completed with failures:" >&2
  printf '  %s\n' "${failures[@]}" >&2
  exit 1
fi

echo ">>> Scaling sweep completed successfully"

#!/usr/bin/env bash
set -euo pipefail

tessi_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
config_dir="$tessi_dir/configs/xem/pnfs_io500_phase1"
artifact_root="/tmp/${USER}/experiments"
stripe_size_mib=${1:-16}
stripe_size_bytes=$((stripe_size_mib * 1024 * 1024))
config_name="transport-rdma_striping-on_ppn-16_mds-round-robin_stripe-size-${stripe_size_bytes}.yaml"
cd "$tessi_dir"

mapfile -t active_status_files < <(
  find "$artifact_root" -path '*/pmanual/artifacts/status/status.phase5' -type f
)
if (( ${#active_status_files[@]} > 1 )); then
  echo "ERROR: found multiple active Phase 5 deployments:" >&2
  printf '  %s\n' "${active_status_files[@]}" >&2
  exit 1
fi
if (( ${#active_status_files[@]} == 1 )); then
  artifact_dir=${active_status_files[0]%/status/status.phase5}
  echo ">>> Cleaning the active deployment: $artifact_dir"
  make -C "$artifact_dir" phase5-clean FORCE=1
fi

"$tessi_dir/configs/xem/generate_pnfs_io500_phase1.py"
config_path="$config_dir/$config_name"

echo ">>> Bootstrapping stripe-size config: $config_path"
"$tessi_dir/bootstrap.sh" "$config_path"

config_hash=$(sha256sum "$config_path" | cut -c1-8)
artifact_dir="$artifact_root/$config_hash/pmanual/artifacts"
test -f "$artifact_dir/Makefile"

echo ">>> Reusing prepared hardware phases 0-4 for hash $config_hash"
make -C "$artifact_dir" -t phase4
printf '%s\n' \
  "Stripe-size screening reused invariant hardware preparation via: make -t phase4" \
  "Configuration: $config_path" \
  > "$artifact_dir/logs/phase0-4-reuse.txt"

echo ">>> Running ${stripe_size_mib} MiB stripe-size configuration (hash $config_hash)"
make -C "$artifact_dir" all

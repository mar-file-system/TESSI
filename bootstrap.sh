#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <inventory-file>" >&2
  exit 1
}

[[ $# -eq 1 ]] || usage

INV="$1"

if [[ ! -f "$INV" ]]; then
  echo "Error: inventory file does not exist: $INV" >&2
  exit 1
fi

if ! command -v ansible-playbook >/dev/null 2>&1; then
  if ! command -v sudo >/dev/null 2>&1 || ! sudo -n true 2>/dev/null; then
    echo "Error: ansible-core is not installed and sudo is not available without a password." >&2
    exit 1
  fi

  if command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y ansible-core
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y ansible-core
  else
    echo "Error: ansible-core is not installed and neither dnf nor apt-get was found." >&2
    exit 1
  fi
fi

if locale -a 2>/dev/null | grep -qi '^C\.UTF-8$'; then
  export LC_ALL=C.UTF-8
  export LANG=C.UTF-8
elif locale -a 2>/dev/null | grep -qi '^en_US\.utf8$'; then
  export LC_ALL=en_US.UTF-8
  export LANG=en_US.UTF-8
else
  echo "Error: no UTF-8 locale found. Ansible requires UTF-8." >&2
  echo "Available locales:" >&2
  locale -a >&2 || true
  exit 1
fi

exec ansible-playbook -i "$INV" playbooks/bootstrap/bootstrap.yaml

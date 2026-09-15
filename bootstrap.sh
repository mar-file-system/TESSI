#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [--make \"target [target ...]\"] <inventory-file>" >&2
  exit 1
}

MAKE_TARGETS=""
#VERBOSE="VERBOSE=1"
VERBOSE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --make)
      [[ $# -ge 2 ]] || usage
      MAKE_TARGETS="$2"
      shift 2
      ;;
    -*)
      usage
      ;;
    *)
      break
      ;;
  esac
done

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

MAKEFILE_DISCOVERY=$(mktemp "${TMPDIR:-/tmp}/tessi-makefile.XXXXXX")
trap 'rm -f "$MAKEFILE_DISCOVERY"' EXIT

ansible-playbook \
  -i "$INV" \
  -e "makefile_discovery=$MAKEFILE_DISCOVERY" \
  playbooks/bootstrap/bootstrap.yaml

if [[ -n "$MAKE_TARGETS" ]]; then
  if [[ ! -s "$MAKEFILE_DISCOVERY" ]]; then
    echo "Error: bootstrap did not report a Makefile path." >&2
    exit 1
  fi

  MAKEFILE=$(<"$MAKEFILE_DISCOVERY")

  if [[ ! -f "$MAKEFILE" ]]; then
    echo "Error: generated Makefile does not exist: $MAKEFILE" >&2
    exit 1
  fi

  make -C "$(dirname "$MAKEFILE")" $MAKE_TARGETS $VERBOSE 
fi

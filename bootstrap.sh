#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [flags] <inventory>" >&2
  echo "flags:" >&2
  echo "        --make \"target [target ...]\"" >&2
  echo "        --preboot preboot-playbook" >&2
  exit 1
}

MAKE_TARGETS=""
PREBOOT_PLAYBOOK=""
#VERBOSE="VERBOSE=1"
VERBOSE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --make)
      [[ $# -ge 2 ]] || usage
      MAKE_TARGETS="$2"
      shift 2
      ;;
    --preboot)
      [[ $# -ge 2 ]] || usage
      PREBOOT_PLAYBOOK="$2"
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
DEFAULT_ANSIBLE_FORKS=128

if [[ ! -f "$INV" && ! -d "$INV" ]]; then
  echo "Error: inventory file does not exist: $INV" >&2
  exit 1
fi
INV=$(realpath "$INV")

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

if ! command -v ansible-inventory >/dev/null 2>&1; then
  echo "Error: ansible-inventory is not installed." >&2
  exit 1
fi

UTF8_LOCALE=$(locale -a 2>/dev/null | awk '
  tolower($0) ~ /^(c|en_us)\.utf-?8$/ && !found { found = $0 }
  END { if (found) print found }
')
if [[ -n "$UTF8_LOCALE" ]]; then
  export LC_ALL="$UTF8_LOCALE"
  export LANG="$UTF8_LOCALE"
else
  echo "Error: no UTF-8 locale found. Ansible requires UTF-8." >&2
  echo "Available locales:" >&2
  locale -a >&2 || true
  exit 1
fi

if ! ansible-inventory -i "$INV" --list >/dev/null; then
  echo "Error: unable to read Ansible inventory: $INV" >&2
  exit 1
fi

FORKS_DISCOVERY=$(mktemp "${TMPDIR:-/tmp}/tessi-forks.XXXXXX")
MAKEFILE_DISCOVERY=$(mktemp "${TMPDIR:-/tmp}/tessi-makefile.XXXXXX")
trap 'rm -f "$FORKS_DISCOVERY" "$MAKEFILE_DISCOVERY"' EXIT

# ansible_forks is an Ansible magic variable and cannot be recovered from
# normalized inventory output. Load the source file into a namespace instead,
# then pass the validated value to the main play under a non-reserved name.
ansible-playbook \
  -i localhost, \
  -e "tessi_inventory_source=$INV" \
  -e "forks_discovery=$FORKS_DISCOVERY" \
  -e "default_ansible_forks=$DEFAULT_ANSIBLE_FORKS" \
  playbooks/bootstrap/read_settings.yaml

ANSIBLE_FORKS=$(<"$FORKS_DISCOVERY")

ansible-playbook \
  -i "$INV" \
  -f "$ANSIBLE_FORKS" \
  -e "tessi_ansible_forks=$ANSIBLE_FORKS" \
  -e "makefile_discovery=$MAKEFILE_DISCOVERY" \
  $PREBOOT_PLAYBOOK \
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

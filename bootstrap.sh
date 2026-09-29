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

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required to read the normalized Ansible inventory." >&2
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

# Ask Ansible to normalize the inventory so this works for both a single
# inventory file and an inventory directory. Parsing the YAML directly here
# would not account for Ansible's inventory plugins or merged group variables.
INVENTORY_JSON=$(mktemp "${TMPDIR:-/tmp}/tessi-inventory.XXXXXX")
trap 'rm -f "$INVENTORY_JSON"' EXIT

if ! ansible-inventory -i "$INV" --list --export > "$INVENTORY_JSON"; then
  echo "Error: unable to read Ansible inventory: $INV" >&2
  exit 1
fi

if ! ANSIBLE_FORKS=$(python3 - "$INVENTORY_JSON" "$DEFAULT_ANSIBLE_FORKS" <<'PY'
import json
import sys

inventory_path, default_forks = sys.argv[1:]
with open(inventory_path, encoding="utf-8") as inventory_file:
    inventory = json.load(inventory_file)

value = inventory.get("all", {}).get("vars", {}).get(
    "ansible_forks", int(default_forks)
)
if isinstance(value, bool) or not isinstance(value, (int, str)):
    sys.exit(1)

text = str(value)
if not text.isdecimal() or int(text) <= 0:
    sys.exit(1)

print(int(text))
PY
); then
  echo "Error: ansible_forks must be a positive integer (default: $DEFAULT_ANSIBLE_FORKS)." >&2
  exit 1
fi

MAKEFILE_DISCOVERY=$(mktemp "${TMPDIR:-/tmp}/tessi-makefile.XXXXXX")
trap 'rm -f "$INVENTORY_JSON" "$MAKEFILE_DISCOVERY"' EXIT

ansible-playbook \
  -i "$INV" \
  -f "$ANSIBLE_FORKS" \
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

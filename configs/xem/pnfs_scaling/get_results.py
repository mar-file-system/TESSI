#!/usr/bin/env python3

import argparse
import re
import subprocess
from pathlib import Path

CONFIG_DIR = Path("configs/xem/pnfs_scaling/scaling_configs")
RESULT_ROOT = Path("/proj/mvpnet/jbent/experiments/pnfs_scaling/pnfs")


def parse_config(path):
    """
    Filename is MDS.DS.CLIENTS.yaml
    """
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)\.yaml", path.name)
    if not m:
        return None

    return tuple(map(int, m.groups()))  # mds, ds, clients


def sort_key(item):
    path, mds, ds, clients = item

    low = min(mds, ds, clients)
    high = max(mds, ds, clients)

    # For a given low count:
    #   clients reduced first
    #   MDS reduced second
    #   DS reduced last
    if clients == low and clients < max(mds, ds):
        kind = 0
    elif mds == low and mds < max(ds, clients):
        kind = 1
    elif ds == low and ds < max(mds, clients):
        kind = 2
    else:
        # Balanced configs like 32.32.32, 16.16.16, etc.
        kind = -1

    return (-low, -high, kind)

def sort_key2(item):
    """
    Order:
      - largest overall scale first
      - full configuration first
      - reduced clients
      - reduced MDS
      - reduced DS
      - larger reduced value before smaller reduced value

    e.g. for the 32-node family:

      32.32.32

      32.32.16
      32.32.8
      32.32.4
      32.32.2

      16.32.32
      8.32.32
      4.32.32
      2.32.32

      32.16.32
      32.8.32
      32.4.32
      32.2.32
    """
    path, mds, ds, clients = item

    scale = max(mds, ds, clients)

    if mds == ds == clients:
        kind = 0
        reduced = scale
    elif mds == scale and ds == scale:
        # Clients reduced
        kind = 1
        reduced = clients
    elif ds == scale and clients == scale:
        # MDS reduced
        kind = 2
        reduced = mds
    elif mds == scale and clients == scale:
        # DS reduced -- deliberately last
        kind = 3
        reduced = ds
    else:
        kind = 4
        reduced = min(mds, ds, clients)

    return (-scale, kind, -reduced)


def find_successful_result(mds, ds, clients):
    pattern = f"clients-{clients}.ds-{ds}.mds-{mds}.physical_hosts-*"

    result_files = []

    for experiment_dir in RESULT_ROOT.glob(pattern):
        result_files.extend(experiment_dir.rglob("result_summary.txt"))

    # Newest first
    result_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for result in result_files:
        try:
            text = result.read_text(errors="replace")
        except OSError:
            continue

        scores = [
            line
            for line in text.splitlines()
            if "SCORE" in line
        ]

        if scores:
            return result, scores

    return None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-missing",
        action="store_true",
        help='Run ./bootstrap.sh CONFIG --make "all phase5-clean" for missing results',
    )
    args = parser.parse_args()

    configs = []

    for path in CONFIG_DIR.glob("*.yaml"):
        parsed = parse_config(path)
        if parsed:
            mds, ds, clients = parsed
            configs.append((path, mds, ds, clients))

    configs.sort(key=sort_key)

    completed=0
    for config, mds, ds, clients in configs:
        result, scores = find_successful_result(mds, ds, clients)

        print(f"MDS {mds}, DS {ds}, Clients {clients}")
        print(result)

        if scores:
            for score in scores:
                print(score)
                completed += 1
        else:
            print("MISSING")

            if args.run_missing:
                cmd = [
                    "./bootstrap.sh",
                    "--make",
                    "all phase5-clean",
                    str(config),
                ]

                print(f"Running: {' '.join(cmd)}")

                print(f"Running: {' '.join(cmd)}", flush=True)

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                for line in process.stdout:
                    print(line, end="", flush=True)

                rc = process.wait()

                if rc != 0:
                    print(f"FAILED: bootstrap exited with {rc}", flush=True)


    print(f"{completed}/{len(configs)} completed so far.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import sys
import os
import json

def main():
    if len(sys.argv) < 3:
        print("Usage: update_env_topology.py <env_file_path> <topology_json_string>")
        sys.exit(1)

    env_file = sys.argv[1]
    try:
        topology = json.loads(sys.argv[2])
    except Exception as e:
        print(f"Error parsing topology JSON: {e}")
        sys.exit(1)

    # Map variables cleanly from your updated set_fact block
    mds_hosts = topology.get("mds_hosts", [])
    mds_ips = topology.get("mds_ips", [])
    rondb_hosts = topology.get("rondb_hosts", [])
    rondb_ips = topology.get("rondb_ips", [])

    # Dynamic free API slot calculations to prevent "No free node id found" panics
    num_mds = len(mds_hosts)
    free_api_slots = (num_mds * 5) + 20

    # Build the exact array items safely without unescaped backslashes
    mds_hosts_str = " ".join([f'"{h}"' for h in mds_hosts])
    mds_ips_str = " ".join([f'"{ip}"' for ip in mds_ips])
    mds_ids_str = " ".join([f'"{i}"' for i in range(num_mds)])

    rondb_hosts_str = " ".join([f'"{h}"' for h in rondb_hosts])
    rondb_ips_str = " ".join([f'"{ip}"' for ip in rondb_ips])
    
    # Calculate Data Node IDs (skiping management node index 0)
    num_data_nodes = max(0, len(rondb_hosts) - 1)
    rondb_node_ids_str = " ".join([f'"{i+1}"' for i in range(num_data_nodes)])

    # Construct the profile string block lines safely
    block_lines = [
        "# --- BEGIN ANSIBLE MANAGED MULTI-MDS & RONDB DYNAMIC TOPOLOGY ---",
        f"LAB_PROFILE_MULTI_MDS_HOSTS=({mds_hosts_str})",
        f"LAB_PROFILE_MULTI_MDS_IPS=({mds_ips_str})",
        f"LAB_PROFILE_MULTI_MDS_IDS=({mds_ids_str})",
        f"LAB_PROFILE_MULTI_RONDB_DATA_HOSTS=({rondb_hosts_str})",
        f"LAB_PROFILE_MULTI_RONDB_DATA_IPS=({rondb_ips_str})",
        f"LAB_PROFILE_MULTI_RONDB_DATA_NODE_IDS=({rondb_node_ids_str})",
        'LAB_PROFILE_MULTI_RONDB_NUM_REPLICAS="2"',
        f'LAB_PROFILE_MULTI_RONDB_FREE_API_SLOTS="{free_api_slots}"',
        'LAB_PROFILE_MULTI_MDS_WORKER_THREADS="8"',
        'LAB_PROFILE_MULTI_MDS_PREALLOC_POOL_SIZE="4096"',
        'LAB_PROFILE_MULTI_TRANSIENT_STATE_CACHE="true"',
        "# --- END ANSIBLE MANAGED MULTI-MDS & RONDB DYNAMIC TOPOLOGY ---"
    ]
    new_block = "\n".join(block_lines) + "\n"

    if not os.path.exists(env_file):
        print(f"Target profile file {env_file} does not exist.")
        sys.exit(1)

    with open(env_file, "r") as f:
        lines = f.readlines()

    # Clean out any previous blocks or residual single line variables
    cleaned_lines = []
    skip_mode = False
    prefixes_to_strip = (
        "LAB_PROFILE_MULTI_MDS_", 
        "LAB_PROFILE_MULTI_RONDB_", 
        "LAB_PROFILE_MULTI_TRANSIENT_STATE_CACHE="
    )

    for line in lines:
        if "BEGIN ANSIBLE MANAGED" in line:
            skip_mode = True
            continue
        if "END ANSIBLE MANAGED" in line:
            skip_mode = False
            continue
        if skip_mode:
            continue
        if line.strip().startswith(prefixes_to_strip):
            continue
        cleaned_lines.append(line)

    content = "".join(cleaned_lines)
    anchor = "# Multi-MDS RonDB lab:"
    
    # Place the new clean topology block directly underneath the anchor section
    if anchor in content:
        parts = content.split(anchor, 1)
        final_output = parts[0] + anchor + "\n\n" + new_block + parts[1]
    else:
        final_output = content + "\n" + new_block

    with open(env_file, "w") as f:
        f.write(final_output)

    print("Successfully synchronized environment topology profiles.")

if __name__ == "__main__":
    main()

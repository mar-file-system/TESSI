#! /bin/env python3

import ansible_runner
from collections import defaultdict

# Define the path to the playbook and the inventory file
playbook_path = './test_striping.yaml'
inventory_path = './hosts.small_lustre.yaml'

# Run the playbook
r = ansible_runner.run(private_data_dir='.', playbook=playbook_path, inventory=inventory_path, quiet=True)

# Iterate through the events

# consolidate tasks and count statuses
task_status_counts = defaultdict(lambda: defaultdict(int))

for event in r.events:
    if event['event'].startswith('runner_on_'):
        task_name = event['event_data']['task']
        host = event['event_data']['host']
        status = event['event'].split('_')[-1].upper()
        task_status_counts[task_name][status] += 1

# Print consolidated task status counts
for task_name, status_counts in task_status_counts.items():
    status_summary = ', '.join([f"{status}: {count}" for status, count in status_counts.items()])
    print(f"Task: {task_name}, Status Counts: {status_summary}")

#print(f"Playbook run status: {r.status}")
#print(f"Playbook run stats: {r.stats}")


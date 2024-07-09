#!/bin/bash

# Function to execute a command and store its return code
run_command() {
    local cmd="$1"
    eval "$cmd" &> /dev/null
    local return_code=$?
    commands_with_rets+=("$cmd: Return code $return_code")
    if [ $return_code -ne 0 ]; then
        error_count=$((error_count + 1))
    fi
    return $return_code
}

# Array to store commands with their return codes
commands_with_rets=()

# Initialize error count
error_count=0

# Array of commands to run
commands=(
    "dig google.com | grep -q 'status: NOERROR'"
    "nslookup google.com"
    "ping -c 1 google.com"
    "nc -z -v -w 5 google.com 80"
    "dig meta00 | grep -q 'status: NOERROR'"
    "dig @192.168.56.1 meta00 | grep -q 'status: NOERROR'"
    "nslookup meta00"
    "ping -c 1 meta00"
    "ssh meta00 hostname"
    "nc -z -v -w 5 meta00 22"
)

# Execute each command and store the return code
for cmd in "${commands[@]}"; do
    run_command "$cmd"
done

# Print the commands and their return codes
for cmd_ret in "${commands_with_rets[@]}"; do
    echo "$cmd_ret"
done

# Print the final error count
echo "$error_count Errors"


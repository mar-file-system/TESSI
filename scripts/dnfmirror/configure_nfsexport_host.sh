#!/bin/env bash
set -e  # Exit on error
set -x  # Echo commands before execution

# Check for required arguments
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <nfs_mount_point> <network> <guest_ip>"
    exit 1
fi

# Assign arguments to variables
NFS_MOUNT_POINT="$1"
NETWORK="$2"
GUEST_IP="$3"

# Check if running as root
IS_ROOT=$(id -u)
SUDO_USER=$(echo $SUDO_USER)

if [ "$IS_ROOT" -ne 0 ]; then
    echo "This script must be run as root. Exiting."
    exit 1
fi

if [ "$IS_ROOT" -eq 0 ] && [ -n "$SUDO_USER" ]; then
    ORIGINAL_USER_HOME=$(eval echo ~$SUDO_USER)
    ORIGINAL_USER_UID=$(stat -c '%u' "$ORIGINAL_USER_HOME")
    ORIGINAL_USER_GID=$(stat -c '%g' "$ORIGINAL_USER_HOME")
    SQUASH_OPTIONS="all_squash,anonuid=$ORIGINAL_USER_UID,anongid=$ORIGINAL_USER_GID"
else
    SQUASH_OPTIONS="no_root_squash"
fi

EXPORT_LINE="$NFS_MOUNT_POINT $NETWORK.$GUEST_IP/24(rw,sync,$SQUASH_OPTIONS,no_subtree_check,fsid=$GUEST_IP)"

# Step 1: Ensure NFS server is running and enabled
IS_ACTIVE=$(sudo systemctl is-active nfs-server || true)
if [ "$IS_ACTIVE" = "inactive" ]; then
    sudo systemctl start nfs-server
    echo "NFS server started."
else
    echo "NFS server already running."
fi

IS_ENABLED=$(sudo systemctl is-enabled nfs-server || true)
if [ "$IS_ENABLED" = "disabled" ]; then
    sudo systemctl enable nfs-server
    echo "NFS server enabled."
else
    echo "NFS server already enabled."
fi

# Step 2: Check and edit /etc/exports to add the export_line if not already present
if [ ! -f /etc/exports ]; then
    echo "/etc/exports not found, creating it."
    sudo touch /etc/exports
fi

if ! grep -qF "$EXPORT_LINE" /etc/exports; then
    echo -e "\n$EXPORT_LINE" | sudo tee -a /etc/exports > /dev/null
    echo "Added $EXPORT_LINE to /etc/exports."

    # Step 3: Reload NFS exports to apply changes
    sudo exportfs -r
    echo "NFS exports reloaded successfully."
else
    echo "$EXPORT_LINE is already present in /etc/exports."
fi


#!/bin/env bash
set -e  # Exit on any error
set -x  # Echo commands before executing them

# Variables
NFS_MNT="192.168.56.1:/mnt/usrc-storage-nfs"
NFS_DIR="/mnt/usrc-storage-nfs"
BASE_MIRROR_DIR="${NFS_DIR}/jbent/dnf"
APACHE_CONF="/etc/httpd/conf.d/dnf-mirror.conf"
MIRROR_REPO_FILE="/etc/yum.repos.d/local-mirror.repo"

# Ensure necessary utilities are installed
dnf install -y httpd createrepo dnf-plugins-core rsync yum-utils nfs-utils

# Ensure NFS mount directory exists
mkdir -p "${NFS_DIR}"

# Ensure NFS directory is mounted
mount -t nfs -o nfsvers=3,noatime,intr,nosuid "${NFS_MNT}" "${NFS_DIR}"

# Ensure the base mirror directory on NFS exists
mkdir -p "${BASE_MIRROR_DIR}"
chmod 755 "${BASE_MIRROR_DIR}"

# Determine OS version (Fedora or AlmaLinux)
if grep -q "Fedora" /etc/os-release; then
    OS_VERSION=$(rpm -E %fedora)
    DISTRO_NAME="fedora-${OS_VERSION}"
elif grep -q "AlmaLinux" /etc/os-release; then
    OS_VERSION=$(rpm -E %rhel)
    DISTRO_NAME="alma-${OS_VERSION}"
else
    echo "Unsupported OS"
    exit 1
fi

# Ensure the distro-specific mirror directory exists
DISTRO_DIR="${BASE_MIRROR_DIR}/${DISTRO_NAME}"
mkdir -p "${DISTRO_DIR}"
chmod 755 "${DISTRO_DIR}"

# Capture dnf repolist all output
REPO_LIST_OUTPUT=$(dnf repolist all)

# Extract repository IDs that contain 'abled' but not 'local'
REPO_IDS=$(echo "$REPO_LIST_OUTPUT" | grep -E 'abled' | grep -v 'local' | awk '{print $1}')

# Sync repositories to the DNF mirror directory
for REPO in ${REPO_IDS}; do
    reposync --download-metadata --repoid="${REPO}" --destdir="${DISTRO_DIR}"
done

# Check if repository metadata already exists
if [ ! -f "${DISTRO_DIR}/repodata/repomd.xml" ]; then
    createrepo "${DISTRO_DIR}"
else
    createrepo --update "${DISTRO_DIR}"
fi

# Disable all other repositories
find /etc/yum.repos.d/ -name "*.repo" -exec sed -i 's/^enabled=.*/enabled=0/' {} +

# Create a repository configuration file for the local DNF mirror
echo "" > "${MIRROR_REPO_FILE}"
for REPO in ${REPO_IDS}; do
    cat <<EOF >> "${MIRROR_REPO_FILE}"
[local-${REPO}]
name=Fedora ${REPO}
baseurl=http://${HOSTNAME}/${DISTRO_NAME}
enabled=1
gpgcheck=0
EOF
done

# Clear DNF cache
dnf clean all

# Ensure Apache is enabled and started
systemctl enable httpd
systemctl start httpd

# Configure Apache for DNF mirror
cat <<EOF > "${APACHE_CONF}"
<VirtualHost *:80>
    DocumentRoot "${BASE_MIRROR_DIR}"
    <Directory "${BASE_MIRROR_DIR}">
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>
</VirtualHost>
EOF

# Restart Apache to apply new configuration
systemctl restart httpd


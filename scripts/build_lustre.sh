#! /usr/bin/bash
set -e
set -x

if [ "$(id -u)" != "0" ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# install lustre dependencies
# https://wiki.lustre.org/Lustre_with_ZFS_Install

echo update dnf 
sudo dnf makecache

echo "Install Lustre dependencies"
dnf -y groupinstall 'Development Tools'
dnf -y install epel-release
dnf -y --enablerepo=powertools install xmlto asciidoc elfutils-libelf-devel zlib-devel kernel-devel libyaml-devel
dnf -y --enablerepo=powertools install binutils-devel newt-devel python3-devel hmaccalc perl-ExtUtils-Embed 
dnf -y install bison elfutils-devel  audit-libs-devel python3-docutils sg3_utils expect 
dnf -y install attr lsof quilt libselinux-devel  
dnf -y --enablerepo=powertools install libmount-devel
dnf -y --enablerepo=powertools install libnl3-cli libnl3-devel

echo "Clone and checkout Lustre 2.15"
git clone git://git.whamcloud.com/fs/lustre-release.git
cd lustre-release
git checkout tags/2.15.4 -b 2.15.4

echo "Build Lustre"
sh autogen.sh; ./configure --with-zfs --disable-ldiskfs --with-linux=/usr/src/kernels/$(uname -r); make -j$(nproc)

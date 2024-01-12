#! /usr/bin/bash

if [ "$(id -u)" != "0" ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# install ZFS dependencies (https://openzfs.github.io/openzfs-docs/Developer%20Resources/Custom%20Packages.html)
dnf install -y --skip-broken epel-release gcc make autoconf automake libtool rpm-build kernel-rpm-macros libtirpc-devel libblkid-devel libuuid-devel libudev-devel openssl-devel zlib-devel libaio-devel libattr-devel elfutils-libelf-devel kernel-devel-$(uname -r) kernel-abi-stablelists-$(uname -r | sed 's/\.[^.]\+$//') python3 python3-devel python3-setuptools python3-cffi libffi-devel ncompress
dnf install -y --skip-broken --enablerepo=epel --enablerepo=powertools python3-packaging dkms

# make sure git is installed
dnf install -y git

# clone and configure and build zfs
git clone https://github.com/openzfs/zfs.git
cd zfs/
git checkout tags/zfs-2.1.11 -b zfs-2.1.11
./autogen.sh; ./configure --with-spec=redhat; make pkg-utils pkg-kmod
dnf localinstall *.$(uname -p).rpm
modprobe zfs

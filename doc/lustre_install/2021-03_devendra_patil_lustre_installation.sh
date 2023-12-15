#!/bin/bash

# Configuring repositories
dnf install 'dnf-command(config-manager)' -y
yum config-manager --set-enabled powertools
yum install epel-release
yum -y groupinstall "Development Tools"


# Downloading dependencies
yum install audit-libs-devel binutils-devel elfutils-devel kabi-dw ncurses-devel newt-devel numactl-devel openssl-devel pciutils-devel perl perl-devel python2 python3-docutils xmlto xz-devel elfutils-libelf-devel libcap-devel libcap-ng-devel llvm-toolset libyaml libyaml-devel kernel-rpm-macros wget c dwarves java-devel libbabeltrace-devel libbpf-devel net-tools python3-devel rsync attr lsof -y

# Downloading kernel packges that are compatible with Lustre version according to Lustre compatibility matrix
wget -r -l1 --no-parent -A kernel*4.18.0-240.1.1.*.rpm  http://mirror.centos.org/centos/8/BaseOS/x86_64/os/Packages/

# Downloading e2fsprogs packages for ldiskfs backend
wget -r -l1 --no-parent -A *1.45.6*.rpm https://downloads.whamcloud.com/public/e2fsprogs/1.45.6.wc5/el8/RPMS/x86_64/

# Installing some dependency
cd /root/mirror.centos.org/centos/8/BaseOS/x86_64/os/Packages && yum install kernel-abi-whitelists-4.18.0-240.1.1.el8_3.noarch.rpm

# Installing all e2fsprogs packages
cd /root/downloads.whamcloud.com/public/e2fsprogs/1.45.6.wc5/el8/RPMS/x86_64 && yum install *.rpm


mkdir /home/build
HOME=/home/build

cd $HOME

# Pulling git repo which  have lustre source package
git clone https://github.com/dspatil7768/lustre_packages.git

cd lustre_packages/

tar -xvf lustre-release-7c0f691.tar.gz

cd lustre-release-7c0f691

# Checking dependency resolution
sh autogen.sh

cd $HOME

mkdir -p kernel/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

cd kernel

echo '%_topdir %(echo $HOME)/kernel/rpmbuild' > ~/.rpmmacros


# Downloading kernel source package required for patching 
wget https://vault.centos.org/8.3.2011/BaseOS/Source/SPackages/kernel-4.18.0-240.1.1.el8_3.src.rpm

# Installing kernel source packages
rpm -ivh kernel-4.18.0-240.1.1.el8_3.src.rpm

cd ~/kernel/rpmbuild/

# building SPEC file
rpmbuild -bp --target=`uname -m` ./SPECS/kernel.spec

######################################################## Patching starts ##############################################################################
cp ~/kernel/rpmbuild/BUILD/kernel-4.18.0-240.1.1.el8_3/linux-4.18.0-240.1.1.el8.x86_64/configs/kernel-4.18.0-x86_64.config ~/lustre_packages/lustre-release-7c0f691/lustre/kernel_patches/kernel_configs/kernel-4.18.0-4.18-rhel8.3-x86_64.config

sed -i '440 a CONFIG_IOSCHED_DEADLINE=y\nCONFIG_DEFAULT_IOSCHED="deadline"' ~/lustre_packages/lustre-release-7c0f691/lustre/kernel_patches/kernel_configs/kernel-4.18.0-4.18-rhel8.3-x86_64.config

cd $HOME

rm -f $HOME/lustre-kernel-aarch64-lustre.patch

cd $HOME/lustre_packages/lustre-release-7c0f691/lustre/kernel_patches/series

for patch in $(<"4.18-rhel8.series"); do patch_file="$HOME/lustre_packages/lustre-release-7c0f691/lustre/kernel_patches/patches/${patch}"; cat "${patch_file}" >> "$HOME/lustre-kernel-x86_84-lustre.patch"; done

cp $HOME/lustre-kernel-x86_84-lustre.patch ~/kernel/rpmbuild/SOURCES/patch-4.18.0-lustre.patch

# Defining ext4 patching in spec file
sed -i '/>modnames/a  \ \ \ \ cp -a fs\/ext4\/* $RPM_BUILD_ROOT\/lib\/modules\/$KernelVer\/build\/fs\/ext4' $HOME/kernel/rpmbuild/SPECS/kernel.spec


sed -i '/empty final patch to facilitate testing of kernel patches/a  # adds Lustre patches\nPatch99995: patch-%{version}-lustre.patch' $HOME/kernel/rpmbuild/SPECS/kernel.spec 

sed -i '/ApplyOptionalPatch linux-kernel-test.patch/a  # lustre patch\nApplyOptionalPatch patch-%{version}-lustre.patch' $HOME/kernel/rpmbuild/SPECS/kernel.spec

echo '# x86_64' > $HOME/kernel/rpmbuild/SOURCES/kernel-4.18.0-aarch64.config

cat $HOME/lustre-release/lustre/kernel_patches/kernel_configs/kernel-4.18.0-4.18-rhel8-aarch64.config >> ~/kernel/rpmbuild/SOURCES/kernel-4.18.0-aarch64.config

cd $HOME/kernel/rpmbuild

buildid="_lustre"


# Building patched kernel RPM
rpmbuild -ba --with firmware --target x86_64 --with baseonly --without kabichk --define "buildid ${buildid}"  $HOME/kernel/rpmbuild/SPECS/kernel.spec

cd $HOME/kernel/rpmbuild/RPMS/x86_64/ && rpm -Uvh *.rpm

cd $HOME/lustre_packages/lustre-release-7c0f691


# Final RPM generation
./configure --with-linux=/home/build/kernel/rpmbuild/BUILD/kernel-4.18.0-240.1.1.el8_3/linux-4.18.0-240.1.1.el8_lustre.x86_64/ &&  make rpms
#####################################################################################################################################################################

















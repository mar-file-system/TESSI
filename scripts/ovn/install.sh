#! /bin/env bash

git clone https://github.com/ovn-org/ovn.git
cd ovn
git checkout v24.09.1
./boot.sh
./configure --with-ovs-source=../../ovs/ovs
make
sudo make install

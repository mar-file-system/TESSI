# TESSI

## Introduction

TESSI (Tool for Extensible Scalable Storage Infrastructure) is designed to assist storage system administrators with the difficult tasks of configuring and testing distributed storage systems. Ultimately, TESSI is intended to enable the testing of multiple different systems such as [BeeGFS](https://www.beegfs.io/c/), [DAOS](https://docs.daos.io/), and [HammerSpace](https://hammerspace.com/), it currently supports [Lustre](https://www.lustre.org/) and BeeGFS.

Additionally, TESSI is intended to work with a variety of physical infrastructures but currently only supports virtual clusters installed using [libvirt](https://libvirt.org/).

The motivation and some additional information about TESSI can be found in our [documents](doc) folder. [Direct link to video](doc/tessi_demo.mov).

## Requirements

1. TESSI has been tested on CentOS 8 running kernel 6.12.5-1.el8.elrepo.x86_64.
2. These instructions correspond to tag _v3.0.0_.
3. TESSI can create a cluster of VMs across a single physical host. 
   - For wider scaling, multiple physical hosts can be used but they need a secondary private network dedicated to TESSI.

## Install
1. Ansible
2. Libvirt
3. Python 3.8
4. qemu-img
5. \> git clone git@gitlab.newmexicoconsortium.org:jbent/tassi.git
6. \> cd tassi 
7. \> git checkout v3.0.0
8. \> pip3.8 install -r requirements.txt

## Running
1. To run TESSI for the first time, make sure you are in the sudoers file.
2. Modify either of the configurations in the configs/ folder. 
3. \> sudo ansible-playbook -i configs/[your_file] ./phases/0_prepare/tassi_prepare.yaml 
4. This will create a Makefile and instructions on using it for the rest of the phases. 

Note that a demo video showing how to run TESSI can be found in our [documents](doc) folder.

## Phases
TESSI runs setup, testing, and reporting as separate phases. Phase 0 is the step documented above. The created Makefile will then allow you to proceed through the following phases:
1. Creation of gold VMs. This creates and stores gold VMs with the necessary software. 
   - For example, the Lustre config creates one gold client image and one gold server image. 
   - Note that the Lustre config supports patching both Lustre itself as well as the ZFS backend.
2. Creation of the virtual networking.
3. Creation of the virtual cluster (i.e. cloning from the gold images).
4. Testing of the virtual network connecting the nodes in the virtual cluster.
5. Configuration of the virtual cluster (e.g. setting up the servers and mounting the clients).
6. Testing of the cluster (e.g. using MPI to run IOR), saving results for reporting.
7. PDF report generation from saved test outputs.
8. Explicit compatibility capture: update the main `compatibility.yaml` after phase7 succeeds.

`make all` runs through phase7; it does not update compatibility records.
Run `make phase8` explicitly to record a successful configuration.
For report-only iteration, use `make phase7-clean phase7`; completed tests are
reused. Editing the report playbook or its template also makes phase7 rebuild.
Regenerate existing Makefiles with `bootstrap.sh` to use this phase layout.
`compatibility.local.yaml` is no longer read or written by compatibility capture.

## Help
For help with TESSI, please create a [new Issue](https://gitlab.newmexicoconsortium.org/jbent/tassi/-/issues/new) in this repo or email jbent@newmexicoconsortium.org.

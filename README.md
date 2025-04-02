# TESSI

## Introduction

TESSI (Tool for Extensible Scalable Storage Infrastructure) is designed to assist storage system administrators with the difficult tasks of configuring and testing distributed storage systems. Ultimately, TESSI is intended to enable the testing of multiple different systems such as [BeeGFS](https://www.beegfs.io/c/), [DAOS](https://docs.daos.io/), and [HammerSpace](https://hammerspace.com/), it currently supports [Lustre](https://www.lustre.org/) and BeeGFS.

Additionally, TESSI is intended to work with a variety of physical infrastructures but currently only supports virtual clusters installed using [libvirt](https://libvirt.org/).

The motivation and some additional information about TESSI can be found in our [documents](doc) folder.

## Requirements

1. TESSI has been tested on CentOS 8 running kernel 6.12.5-1.el8.elrepo.x86_64.
2. These instructions correspond to tag _v2.0.0_.
3. TESSI can create a cluster of VMs across a single physical host. For wider scaling, multiple physical hosts can be used but they need a secondary private network dedicated to TESSI.

## Install
1. Ansible
2. Libvirt
3. Python 3.8

## Running
1. To run TESSI for the first time, make sure you are in the sudoers file.
2. Modify either of the configurations in the configs/ folder. 
3. > sudo ansible-playbook -i configs/[your_file] ./phases/0_prepare/tassi_prepare.yaml 
4. This will produce a Makefile and will output instructions about how to use that Makefile to proceed through the remainder of the phases.

Note that a demo video showing how to run TESSI can be found in our [documents](doc) folder.

## Phases
TESSI runs in five main phases. Phase 0 is the step documented above. The created Makefile will then allow you to proceed through the following phases:
1. Creation of gold VMs. This creates and stores gold VMs with the necessary software. 
   - For example, the Lustre config creates one gold client image and one gold server image. 
   - Note that the Lustre config supports patching both Lustre itself as well as the ZFS backend.
2. Creation of the virtual networking.
3. Creation of the virtual cluster (i.e. cloning from the gold images).
4. Testing of the virtual network connecting the nodes in the virtual cluster.
5. Configuration of the virtual cluster (e.g. setting up the servers and mounting the clients).
6. Testing of the virtual cluster (e.g. using MPI to run IOR).

## Help
For help with TESSI, please create a [new Issue](https://gitlab.newmexicoconsortium.org/jbent/tassi/-/issues/new) in this repo or email jbent@newmexicoconsortium.org.

<!--

## Integrate with your tools

- [ ] [Set up project integrations](https://gitlab.newmexicoconsortium.org/jbent/tassi/-/settings/integrations)

## Collaborate with your team

- [ ] [Invite team members and collaborators](https://docs.gitlab.com/ee/user/project/members/)
- [ ] [Create a new merge request](https://docs.gitlab.com/ee/user/project/merge_requests/creating_merge_requests.html)
- [ ] [Automatically close issues from merge requests](https://docs.gitlab.com/ee/user/project/issues/managing_issues.html#closing-issues-automatically)
- [ ] [Enable merge request approvals](https://docs.gitlab.com/ee/user/project/merge_requests/approvals/)
- [ ] [Automatically merge when pipeline succeeds](https://docs.gitlab.com/ee/user/project/merge_requests/merge_when_pipeline_succeeds.html)

## Test and Deploy

Use the built-in continuous integration in GitLab.

- [ ] [Get started with GitLab CI/CD](https://docs.gitlab.com/ee/ci/quick_start/index.html)
- [ ] [Analyze your code for known vulnerabilities with Static Application Security Testing(SAST)](https://docs.gitlab.com/ee/user/application_security/sast/)
- [ ] [Deploy to Kubernetes, Amazon EC2, or Amazon ECS using Auto Deploy](https://docs.gitlab.com/ee/topics/autodevops/requirements.html)
- [ ] [Use pull-based deployments for improved Kubernetes management](https://docs.gitlab.com/ee/user/clusters/agent/)
- [ ] [Set up protected environments](https://docs.gitlab.com/ee/ci/environments/protected_environments.html)
-->


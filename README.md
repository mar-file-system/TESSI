# TASSI

## Introduction

TASSI (Tool for Agile Scalable Storage Infrastructure) is designed to assist storage system administrators with the difficult tasks of configuring and testing distributed storage systems. Ultimately, TASSI is intended to enable the testing of multiple different systems such as [BeeGFS](https://www.beegfs.io/c/), [DAOS](https://docs.daos.io/), and [HammerSpace](https://hammerspace.com/), it currently only supports [Lustre](https://www.lustre.org/).

Additionally, TASSI is intended to work with a variety of physical infrastructures but currently only supports virtual clusters installed using [libvirt](https://libvirt.org/).

The motivation and some additional information about TASSI can be found in our [documents](doc) folder.

## Requirements

1. TASSI has been tested on CentOS Linux release 8.5.2111 running kernel 4.18.0-348.el8.x86_64.
2. These instructions correspond to tag _v1.0.0_.

## Install
1. cd setup
2. sudo ./setup_tassi.sh 

## Running
1. To run TASSI for the first time, make sure you are in the sudoers file.
2. _cd scripts_
3. Edit [scripts/ansible/autotest.4c2m2o.yaml](scripts/ansible/autotest.4c2m2o.yaml) and [scripts/ansible/autotest.2c2m2o.yaml](scripts/ansible/autotest.2c2m2o.yaml) to set the _auth_keys_ line appropriately for you.
4. Run the [scripts/auto_git.py](scripts/auto_git.py) script which will automatically run all test configurations in the ansible folder with an _autotest_ prefix.
5. To re-run any tests, merely commit changes to these files or create new ones.
6. [scripts/list_vms.py](scripts/list_vms.py) is a useful tool to show the status of your current virtual machines.
7. You can also directly test the system (without using the auto_git.py) tool by running [scripts/setup_lustre_cluster.py](scripts/setup_lustre_cluster.py).

## Help
For help with TASSI, please create a [new Issue](https://gitlab.newmexicoconsortium.org/jbent/tassi/-/issues/new) in this repo or email jbent@newmexicoconsortium.org.

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


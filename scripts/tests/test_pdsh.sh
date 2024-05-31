#!/bin/bash

# allow extra args to be passed 
myargs=$@

# Arguments for ssh and IOR command
ssh_args="-o StrictHostKeyChecking=no"

# Execute the command on the remote host
ssh $ssh_args client00 "pdsh -w ${myargs} hostname"

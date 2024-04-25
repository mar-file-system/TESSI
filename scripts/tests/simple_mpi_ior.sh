#!/bin/bash

# Environment variables for MPI
mpi_env_vars="export OMPI_MCA_pml=ob1; export OMPI_MCA_btl=tcp,self;"

# Arguments for ssh and IOR command
ssh_args="-o StrictHostKeyChecking=no"
ior_args="--allow-run-as-root -np 2 ior -o /mnt/lustre/testfile -host client01,client00 -t 1m -b 16m -s 16"

# Execute the command on the remote host
ssh $ssh_args client00 "${mpi_env_vars} mpirun ${ior_args}"

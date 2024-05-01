#!/bin/bash

# Environment variables for MPI
mpi_env_vars="export OMPI_MCA_pml=ob1; export OMPI_MCA_btl=tcp,self;"

# Arguments for ssh and IOR command
ssh_args="-o StrictHostKeyChecking=no"
mpi_args="--allow-run-as-root -np 8 -host client00,client01,client02,client03,client04,client05,client06,client07"
ior_args="-o /mnt/lustre/testfile -t 1m -b 16m -s 16"

# Execute the command on the remote host
ssh $ssh_args client00 "${mpi_env_vars} mpirun $mpi_args ior ${ior_args}"

#! /usr/bin/env python3

import argparse
import os
import subprocess

def run_command(no_exec, command):
    print(f"COMMAND: {command}")
    if not no_exec:
        subprocess.run(command, shell=True, check=True)
        print(f"{'-' * 80}")

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Use ssh to mpirun IOR test on remote host(s).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-ma', '--mpi_args', default='--allow-run-as-root', help="Args to pass to mpirun")
    parser.add_argument('-me', '--mpi_env', default='export OMPI_MCA_pml=ob1; export OMPI_MCA_btl=tcp,self;', help="Env vars to pass to mpi")
    parser.add_argument('-sa', '--ssh_args', default='-o StrictHostKeyChecking=no', help='Args to ssh')
    parser.add_argument('-ia', '--ior_args', default='-t 1m -b 16m -s 16', help='Args to ior')
    parser.add_argument('-tf', '--test_file', default='/mnt/beegfs/testfile', help='Target file') 
    parser.add_argument('-mh', '--mpi_hosts', default='client00,client01', help='Hosts for the mpirun')
    parser.add_argument('-sh', '--ssh_host', default='client00', help='Hosts for the ssh command')
    parser.add_argument('-ph', '--pdsh_hosts', default=None, type=str, help='Optional list of hosts to pass to an optional precursor pdsh test')
    parser.add_argument('-pc', '--pdsh_command', default='hostname', help='What pdsh command to run if pdsh_hosts is set')
    parser.add_argument('-ne', '--no_exec', default=False, action='store_true', help='Do not execute. Just print the command that would be executed and exit')
    args = parser.parse_args()

    if args.pdsh_hosts:
        ssh_command = f"ssh {args.ssh_args} {args.ssh_host} \"pdsh -w {args.pdsh_hosts} {args.pdsh_command}\""
        run_command(args.no_exec, ssh_command)

    ior_args = f"-o {args.test_file} {args.ior_args}"
    ior_command = f"ior -o {args.test_file} {args.ior_args}"

    np = len(args.mpi_hosts.split(','))
    mpi_command = f"{args.mpi_env} mpirun {args.mpi_args} -np {np} -host {args.mpi_hosts} {ior_command}"

    ssh_command = f"ssh {args.ssh_args} {args.ssh_host} \"{mpi_command}\""
    run_command(args.no_exec, ssh_command)

if __name__ == "__main__":
    main()


# Shared MPI tasks

Use the common tasks for benchmark launches rather than repeating MPI flags:

1. `discover_mpi.yaml` loads the selected module through
   `run_with_mpi_module.yaml` and returns `mpi_bin` and `mpi_label`.
   Input: `mpi: {module: mpi/openmpi-x86_64}`.
2. `write_mpi_hostfile.yaml` writes hosts and optional per-host slot counts.
   Inputs: `mpi_module`, `hosts`, `hostfile_path`, optional `slots_by_host`.
3. `build_mpi_command.yaml` returns `mpi_launcher_argv` and its shell-quoted
   equivalent `mpi_launcher_command`. Inputs: `mpi_launcher_module`, the
   discovered `mpi_bin`, optional `mpi_launcher_hostfile`, and optional
   `mpi_launcher_extra_args` (an argv list).
4. Execute `mpi_launcher_command` plus the benchmark's rank count, arguments
   and optional implementation-specific transport settings with
   `run_with_mpi_module.yaml`. Python schedulers receive `mpi_launcher_argv`
   and use subprocess argument lists. Keep the MPI module loaded while running.

The builder centralizes Open MPI's install prefix, remote SSH options,
root execution support, and full-hostname preservation. MPICH does not receive
Open MPI flags. Rank placement and transport remain benchmark-specific.
Caller-provided `mpirun_args` strings remain supported for existing configs.

Installation uses `register_rpm_openmpi.yaml` for both DOCA's combined package
and Rocky's split openmpi/openmpi-devel packages. Inputs are
`openmpi_module_name` and optional `openmpi_module_env_vars`.
`osu_paths.yaml` resolves OSU paths for installation and execution from
`osu_mpi_module`; use its `osu_install_prefix` and `osu_binary_dir` outputs.

Local regression checks (no MPI or cluster required):

```sh
python3 -m unittest discover -s tests/unit
ansible-playbook -i localhost, tests/ansible/test_mpi_launcher.yaml
```

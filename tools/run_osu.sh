#!/usr/bin/env bash
set -euo pipefail

############################
# USER-TUNABLE PARAMETERS  #
############################

PPN=4
NODE_PREFIX="hs"
FIRST_NODE=145
LAST_NODE=160

RESULTS_BASE="/mnt/usrc-storage-nfs/jbent/osu_results/hellscape_direct"
HOSTFILE="/tmp/hosts.${NODE_PREFIX}.${FIRST_NODE}-${LAST_NODE}"

BENCHMARKS=(
  mpi/startup/osu_hello
  mpi/pt2pt/osu_latency
  mpi/pt2pt/osu_bw
  mpi/collective/osu_allreduce
  mpi/collective/osu_alltoall
  mpi/one-sided/osu_put_bw
  mpi/one-sided/osu_get_latency
)

############################
# BUILD HOSTFILE           #
############################

echo "Building hostfile at ${HOSTFILE}"
rm -f "${HOSTFILE}"

for ((i=FIRST_NODE; i<=LAST_NODE; i++)); do
  echo "${NODE_PREFIX}${i}" >> "${HOSTFILE}"
done

NODE_COUNT=$(wc -l < "${HOSTFILE}")
NP=$(( NODE_COUNT * PPN ))

echo "Nodes: ${NODE_COUNT}"
echo "PPN:   ${PPN}"
echo "Total ranks: ${NP}"
echo "Hostfile:"
cat "${HOSTFILE}"
echo

############################
# BENCHMARK FUNCTION      #
############################

run_benchmarks() {
  local label="$1"
  local mpirun_cmd="$2"
  local osu_root="$3"
  local ts=`date`
  local ss=`date +%s`

  local outdir="${RESULTS_BASE}/${label}.${ss}"
  mkdir -p "$outdir"

  echo "=========================================="
  echo "Running benchmarks for: $label"
  echo "Output dir: $outdir"
  echo "=========================================="

  echo "${mpirun_cmd}" > "$outdir/SUMMARY"
  echo "${ts}" >> "$outdir/SUMMARY"

  for bench in "${BENCHMARKS[@]}"; do
    local bench_name
    bench_name="$(basename "$bench")"
    local bench_path="${osu_root}/${bench}"
    local run_cmd="${mpirun_cmd}"

    # pt2pt and one-sided benchmarks must run with np=2 and ppn=1
    if [[ "$bench" == *"/pt2pt/"* || "$bench" == *"/one-sided/"* ]]; then
      run_cmd="${run_cmd/ -np ${NP} / -np 2 }"
      run_cmd="${run_cmd/ -ppn ${PPN} / -ppn 1 }"
      run_cmd="${run_cmd/ --map-by ppr:4:node / --map-by ppr:1:node }"
    fi

    echo "--- ${bench_name} ---"
    echo "${run_cmd} ${bench_path} > ${outdir}/${bench_name}"

    ${run_cmd} "${bench_path}" \
      | tee "${outdir}/${bench_name}"
  done
}

########################################
# 1. OPEN MPI — TCP over eno1           #
########################################

module purge
module load mpi/openmpi

OPENMPI_TCP_CMD="mpirun -np ${NP} \
  -hostfile ${HOSTFILE} \
  --map-by ppr:${PPN}:node \
  --bind-to core \
  --mca pml ob1 \
  --mca btl tcp,self \
  --mca btl_tcp_if_include eno1 \
  --mca mtl ^ofi"

run_benchmarks \
  "openmpi_tcp_eno1_phyhosts_${NODE_COUNT}_ppn_${PPN}" \
  "${OPENMPI_TCP_CMD}" \
  "/usr/local/osu/mpi_openmpi/libexec/osu-micro-benchmarks"

########################################
# 2. OPEN MPI — UCX over enp65s0np0     #
########################################

OPENMPI_UCX_CMD="mpirun -np ${NP} \
  -hostfile ${HOSTFILE} \
  --map-by ppr:${PPN}:node \
  --bind-to core \
  --mca pml ucx \
  --mca osc ucx \
  --mca btl ^tcp \
  --mca mtl ^ofi \
  --mca ucx_net_devices enp65s0np0"

run_benchmarks \
  "openmpi_ucx_enp65s0np0_phyhosts_${NODE_COUNT}_ppn_${PPN}" \
  "${OPENMPI_UCX_CMD}" \
  "/usr/local/osu/mpi_openmpi/libexec/osu-micro-benchmarks"

########################################
# 3. MVAPICH2                           #
########################################

module purge
module load mpi/mvapich2

export MV2_USE_RDMA_CM=1
export MV2_ENABLE_AFFINITY=1

MVAPICH_CMD="mpirun -np ${NP} \
  -ppn ${PPN} \
  -hostfile ${HOSTFILE}"

run_benchmarks \
  "mvapich2_phyhosts_${NODE_COUNT}_ppn_${PPN}" \
  "${MVAPICH_CMD}" \
  "/usr/local/osu/mpi_mvapich2/libexec/osu-micro-benchmarks"

echo
echo "All benchmarks complete."


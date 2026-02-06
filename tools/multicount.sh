#!/bin/bash

prev_eno1=0
prev_ib=0

tot_eno1=0
tot_ib=0

while true; do
  cur_eno1=$(( \
    $(cat /sys/class/net/eno1/statistics/rx_packets) + \
    $(cat /sys/class/net/eno1/statistics/tx_packets) \
  ))

  cur_ib=$(( \
    $(cat /sys/class/net/enp65s0np0/statistics/rx_packets) + \
    $(cat /sys/class/net/enp65s0np0/statistics/tx_packets) \
  ))

  # First iteration: establish baseline
  if [[ $prev_eno1 -eq 0 ]]; then
    prev_eno1=$cur_eno1
    prev_ib=$cur_ib
    sleep 3
    continue
  fi

  d_eno1=$((cur_eno1 - prev_eno1))
  d_ib=$((cur_ib - prev_ib))

  tot_eno1=$((tot_eno1 + d_eno1))
  tot_ib=$((tot_ib + d_ib))

  printf "eno1: Δ=%10d | Σ=%8.1e   ||   enp65s0np0: Δ=%10d | Σ=%8.1e\n" \
    $d_eno1 $tot_eno1 \
    $d_ib $tot_ib

  prev_eno1=$cur_eno1
  prev_ib=$cur_ib

  sleep 3
done


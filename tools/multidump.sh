#!/usr/bin/env bash

# to use this create a file called 'foo' or whatever
# that looks like this:
# 
"""
quilt01:wg-bquilt_wire:icmp
quilt05:wg-bquilt_wire:icmp
quilt01:eno1:udp:42054
quilt05:eno1:udp:37825
"""
# then call this with 'foo' as an argument and it will tcpdump all of those optionally filtering on a port
# this is useful for figuring out where a packet is dropped when it is traversing lots of networks

CONFIG_FILE="$1"
declare -A HOSTS

# Start tcpdump streams
while IFS=: read -r HOST IFACE FILTER PORT LEN; do
    [[ -z "$HOST" || "$HOST" =~ ^# ]] && continue

    HOSTS["$HOST"]=1   # record host

    TCPDUMP_FILTER="$FILTER"

    [[ -n "$PORT" ]] && TCPDUMP_FILTER="$TCPDUMP_FILTER and port $PORT"
    [[ -n "$LEN"  ]] && TCPDUMP_FILTER="$TCPDUMP_FILTER and less $LEN"

    ssh -o BatchMode=yes "$HOST" \
        "sudo stdbuf -oL tcpdump -n -i $IFACE '$TCPDUMP_FILTER'" \
        | sed "s/^/[$HOST $IFACE $FILTER${PORT:+:$PORT}${LEN:+:$LEN}] /" &
done < "$CONFIG_FILE"

echo "Press Ctrl-C to stop captures."

# IMPORTANT: single quotes prevent premature expansion
trap 'echo; echo "Stopping captures..."; \
      for H in "${!HOSTS[@]}"; do \
          echo "Killing tcpdump on $H"; \
          ssh -o BatchMode=yes "$H" "sudo killall -q tcpdump"; \
      done; exit 0' INT

wait


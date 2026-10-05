#!/usr/bin/env bash
set -euo pipefail

M=32
D=32
C=32

TEMPLATE="MM.DD.CC.yaml"
CDIR="scaling_configs"

mkdir -p $CDIR 

generate() {
    local m=$1
    local d=$2
    local c=$3
    local outfile="$CDIR/${m}.${d}.${c}.yaml"

    sed \
        -e "s/MM/$((m - 1))/g" \
        -e "s/DD/$((d - 1))/g" \
        -e "s/CC/$((c - 1))/g" \
        "$TEMPLATE" > "$outfile"

    echo "Created $outfile"
}

# Scale all three together.
n=2
while (( n <= M && n <= D && n <= C )); do
    generate "$n" "$n" "$n"
    (( n *= 2 ))
done

# Scale MDS with DS and clients maximized.
n=2
while (( n < M )); do
    generate "$n" "$D" "$C"
    (( n *= 2 ))
done

# Scale DS with MDS and clients maximized.
n=2
while (( n < D )); do
    generate "$M" "$n" "$C"
    (( n *= 2 ))
done

# Scale clients with MDS and DS maximized.
n=2
while (( n < C )); do
    generate "$M" "$D" "$n"
    (( n *= 2 ))
done

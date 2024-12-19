#! /bin/env bash

set -e  # Exit immediately on error
set -x  # Echo each command

source variables.sh
source clean_network.sh

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root. Please use sudo."
    exit 1
fi

ip link add dev $INTERFACE type wireguard
ip address add dev wg0 $IPRANGE 

wg genkey > $PRIV_KEY
wg pubkey < $PRIV_KEY
wg set $INTERFACE private-key $PRIV_KEY
ip link set $INTERFACE up

# echo now you have to exchange the info between nodes
# watch the top video here: https://www.wireguard.com/quickstart/

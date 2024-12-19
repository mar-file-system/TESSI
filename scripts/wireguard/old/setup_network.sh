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

wg show
ip address show eno1

echo Get the public key from peers and then for each one run the following:
echo wg set $INTERFACE peer _PEER_KEY_ allowed-ips _PEER_WG_IP_/32 end point _PEER_PUBLIC_IP_:_PEER_WG_LISTENING_PORT_

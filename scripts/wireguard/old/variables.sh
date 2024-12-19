BASE_IP="192.68.2"
INTERFACE=wg0
PRIV_KEY=/tmp/private

# Get the current hostname
HOSTNAME=$(hostname)

# Define host-to-last-octet mappings
declare -A HOST_TO_LAST_OCTET=(
    ["in16"]="1"
    ["in07"]="2"
    ["in15"]="3"
)

# Loop through the mappings to set IPRANGE
if [[ -n ${HOST_TO_LAST_OCTET[$HOSTNAME]} ]]; then
    IPRANGE="${BASE_IP}.${HOST_TO_LAST_OCTET[$HOSTNAME]}/24"
    echo "IPRANGE set to $IPRANGE for host $HOSTNAME"
else
    echo "Error: Unknown host $HOSTNAME"
    exit 1
fi


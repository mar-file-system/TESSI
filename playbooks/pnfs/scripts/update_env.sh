#!/bin/bash
ENV_FILE="$1"

# Map live incoming arguments
MDS_HOSTS=($2)
MDS_IPS=($3)

NUM_MDS=${#MDS_HOSTS[@]}
FREE_API_SLOTS=$((NUM_MDS * 5 + 20))

# Logic: RonDB data hosts are all EXCEPT the last one (reserved for MGM)
NUM_RONDB=$(( NUM_MDS > 1 ? NUM_MDS - 1 : 1 ))

# Slice arrays: 
# MDS_HOSTS[:] is full list
# RONDB_HOSTS=(${MDS_HOSTS[@]:0:$NUM_RONDB}) slices from index 0 up to count
RONDB_HOSTS=("${MDS_HOSTS[@]:0:$NUM_RONDB}")
RONDB_IPS=("${MDS_IPS[@]:0:$NUM_RONDB}")

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: Target file $ENV_FILE not found." >&2
    exit 1
fi

replace_array() {
    local var_name="$1"
    shift
    local elements=("$@")
    echo "${var_name}=("
    for item in "${elements[@]}"; do
        echo "    \"$item\""
    done
    echo ")"
    while [[ "$line" != *")"* ]]; do IFS= read -r line || break; done
}

while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^LAB_PROFILE_DEFAULT= ]]; then
        echo 'LAB_PROFILE_DEFAULT="multi-mds"'
        continue
    fi
    if [[ "$line" =~ ^LAB_PROFILE_MULTI_RONDB_FREE_API_SLOTS= ]]; then
        echo "LAB_PROFILE_MULTI_RONDB_FREE_API_SLOTS=\"$FREE_API_SLOTS\""
        continue
    fi
    
    # Map arrays
    if [[ "$line" =~ ^LAB_PROFILE_MULTI_MDS_HOSTS=\( ]]; then
        replace_array "LAB_PROFILE_MULTI_MDS_HOSTS" "${MDS_HOSTS[@]}"
        continue
    fi
    if [[ "$line" =~ ^LAB_PROFILE_MULTI_MDS_IPS=\( ]]; then
        replace_array "LAB_PROFILE_MULTI_MDS_IPS" "${MDS_IPS[@]}"
        continue
    fi
    if [[ "$line" =~ ^LAB_PROFILE_MULTI_MDS_IDS=\( ]]; then
        ids=()
        for ((i=1; i<=NUM_MDS; i++)); do ids+=("$i"); done
        replace_array "LAB_PROFILE_MULTI_MDS_IDS" "${ids[@]}"
        continue
    fi

    if [[ "$line" =~ ^LAB_PROFILE_MULTI_RONDB_DATA_HOSTS=\( ]]; then
        replace_array "LAB_PROFILE_MULTI_RONDB_DATA_HOSTS" "${RONDB_HOSTS[@]}"
        continue
    fi
    if [[ "$line" =~ ^LAB_PROFILE_MULTI_RONDB_DATA_IPS=\( ]]; then
        replace_array "LAB_PROFILE_MULTI_RONDB_DATA_IPS" "${RONDB_IPS[@]}"
        continue
    fi
    if [[ "$line" =~ ^LAB_PROFILE_MULTI_RONDB_DATA_NODE_IDS=\( ]]; then
        ids=()
        for ((i=1; i<=${#RONDB_HOSTS[@]}; i++)); do ids+=("$i"); done
        replace_array "LAB_PROFILE_MULTI_RONDB_DATA_NODE_IDS" "${ids[@]}"
        continue
    fi

    echo "$line"
done < "$ENV_FILE"

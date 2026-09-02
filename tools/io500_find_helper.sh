#!/bin/bash

# 1. Base test directory setup
TARGET_DIR="/mnt/pnfs/$USER/io500_test"
TIMESTAMP_DIR="$TARGET_DIR/timestamp_holder"

echo "Creating base test environment at: $TARGET_DIR"
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"
mkdir -p "$TIMESTAMP_DIR"

# 2. Create random subdirectories
SUBDIRS=("$TARGET_DIR/alpha" "$TARGET_DIR/beta" "$TARGET_DIR/gamma" "$TARGET_DIR/delta")
for dir in "${SUBDIRS[@]}"; do
    mkdir -p "$dir"
done

# 3. Create 100 files (OLD) that should NEVER match the -newer constraint
echo "Generating 100 historical baseline files..."
for i in {1..100}; do
    # Alternate across subdirectories to mimic a distributed walk
    CURRENT_DIR=${SUBDIRS[$((i % 4))]}
    
    if [ $((i % 2)) -eq 0 ]; then
        # Half are matching name and size, but will be too old
        truncate -s 3901 "$CURRENT_DIR/no.old_match_01_$i"
    else
        # Half are non-matching junk
        truncate -s 1024 "$CURRENT_DIR/no.old_junk_$i"
    fi
done

# Ensure filesystem shifts forward in time before timestamp generation
sleep 1

# 4. Create the reference timestamp file
TIMESTAMP_FILE="$TIMESTAMP_DIR/timestampfile"
touch "$TIMESTAMP_FILE"
echo "Timestamp reference file created at: $TIMESTAMP_FILE"

# Ensure filesystem shifts forward so subsequent files are strictly newer
sleep 1

# 5. Create the 4 distinct test cohorts (NEW)
echo "Generating test cohorts..."
for i in {1..100}; do
    CURRENT_DIR=${SUBDIRS[$((i % 4))]}

    # Cohort A: Name does NOT match *01*, Size matches 3901c (Result: NO)
    truncate -s 3901 "$CURRENT_DIR/no.size_only_$i"

    # Cohort B: Name matches *01*, Size does NOT match 3901c (Result: NO)
    truncate -s 1024 "$CURRENT_DIR/no.name_only_01_$i"

    # Cohort C: Name does NOT match *01*, Size does NOT match 3901c (Result: NO)
    truncate -s 500 "$CURRENT_DIR/no.junk_$i"

    # Cohort D: Name matches *01* AND Size matches 3901c (Result: YES)
    truncate -s 3901 "$CURRENT_DIR/yes.true_match_01_$i"
done

echo "-------------------------------------------------------"
echo "Setup complete. Run your test with the exact command below:"
echo ""
echo "./pfind $TARGET_DIR -newer $TIMESTAMP_FILE -size 3901c -name '*01*' -C -q 10000"
echo "-------------------------------------------------------"
echo "Expected validation result: Exactly 100 files matching 'yes.true_match_01_*' should be returned."


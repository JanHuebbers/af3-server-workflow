#!/usr/bin/env bash
# This script allows batch input of multiple Run configurations to generate input files for AF3 modeling.
# Run from project root:
#   ./src/shell/batch_module1.sh

set -euo pipefail

CHAIN1=(AtMLO1, AtMLO2)

# Chain 2 = EXO70s (10) — phylogeny order
CHAIN2=(AtCAM2)

RUNID_NUM=164

for c1 in "${CHAIN1[@]}"; do
  for c2 in "${CHAIN2[@]}"; do
    RUNID=$(printf "%04d" "$RUNID_NUM")
    RUNNAME="Run${RUNID}_1${c1}_1${c2}"
    CFG="config/${RUNNAME}.yml"

    echo "==> ${RUNNAME}"
    [[ -f "$CFG" ]] || { echo "ERROR: Missing $CFG" >&2; exit 1; }

    python src/_010_run_create_input.py "${RUNNAME}"
    RUNID_NUM=$((RUNID_NUM + 1))
  done
done
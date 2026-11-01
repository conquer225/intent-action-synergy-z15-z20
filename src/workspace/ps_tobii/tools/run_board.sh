#!/bin/sh
# Finite diagnostic capture. No boot/overlay/network/calibration writes.
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$task_dir"
if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'Run with sudo sh run_board.sh [probe arguments].' >&2
    exit 1
fi
ulimit -s 32768
run_dir=/dev/shm/tobii_z15/current
mkdir -p "$run_dir/frames"
printf 'Board RAM output: %s\n' "$run_dir"
exec ./is4-probe --startup tobiifree --streams 0501 --seconds 120 \
    --image-write-hz 1 --image-ring-size 2 --csv "$run_dir/gaze.csv" \
    --out "$run_dir/frames" "$@"

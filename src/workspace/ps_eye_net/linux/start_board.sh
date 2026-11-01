#!/bin/sh
set -eu
TASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$TASK_DIR"
python3 linux/check_environment.py --probe-cma "$@"
exec python3 -u linux/board_service.py "$@"

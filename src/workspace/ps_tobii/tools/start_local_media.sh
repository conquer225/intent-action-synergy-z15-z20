#!/bin/sh
# Run from the existing /home/xilinx/tobii_z15 install; no boot/service changes.
set -eu
cd /home/xilinx/tobii_z15
if ! sh tools/setup_usb_audio.sh; then
    printf '%s\n' 'USB audio driver unavailable; menu/video remain usable, audio requires setup' >&2
fi
exec sh display_session.sh guide --local-media "$@"

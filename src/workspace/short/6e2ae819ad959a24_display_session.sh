#!/bin/sh
# Temporarily exclude the current EEG runtime; preserve its enablement/files.
set -u
cd /home/xilinx/tobii_z15 || exit 1
was_active=$(systemctl is-active guardianloop-cyton.service || true)
python=/usr/local/share/pynq-venv/bin/python3
original=$(env XILINX_XRT=/usr "$python" -c 'from pynq import PL; print(PL.bitfile_name)') || exit 1
printf 'previous_cyton=%s original=%s\n' "$was_active" "$original"
restore_service() {
    current=$(env XILINX_XRT=/usr "$python" -c 'from pynq import PL; print(PL.bitfile_name)') || return
    if [ "$current" = "$original" ] && { [ "$was_active" = active ] || [ "$was_active" = activating ]; }; then
        systemctl start guardianloop-cyton.service
        printf '%s\n' 'previous_cyton_restored'
    elif [ "$current" != "$original" ]; then
        printf '%s\n' 'PL restoration not verified; EEG runtime left stopped' >&2
    fi
}
trap restore_service EXIT
systemctl stop guardianloop-cyton.service || exit 1
if systemctl is-active --quiet guardianloop-cyton.service; then exit 1; fi
program=src/display_probe.py
if [ "${1:-}" = guide ]; then program=src/hdmi_guide.py; shift; fi
if [ "${1:-}" = media-check ]; then program=tools/check_local_media_board.py; shift; fi
env XILINX_XRT=/usr "$python" -u "$program" "$@"

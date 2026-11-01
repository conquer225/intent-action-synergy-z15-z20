#!/bin/sh
# Optional offline rebuild using the installed kernel headers and bundled sources.
set -eu
cd /home/xilinx/tobii_z15
kernel=$(uname -r)
if [ "$kernel" != 5.4.0-xilinx-v2020.2 ]; then
    printf 'Bundled sources were prepared for 5.4.0-xilinx-v2020.2, current %s\n' "$kernel" >&2
    exit 1
fi
work=$(mktemp -d /home/xilinx/tobii_z15/usb-audio-build.XXXXXX)
mkdir "$work/headers"
cp -a "/lib/modules/$kernel/build/." "$work/headers/"
tar -xzf drivers/usb_audio_source.tar.gz -C "$work"
# PYNQ clocks may be unset; normalize this private copy, never system headers.
python3 - "$work" <<'PY'
import os, sys, time
from pathlib import Path
now = time.time()
for path in Path(sys.argv[1]).rglob('*'):
    if path.is_file():
        os.utime(str(path), (now, now))
PY
make -C "$work/headers" ARCH=arm prepare scripts
make -C "$work/headers" ARCH=arm M="$work/usb_audio_source" -j2 modules
mkdir -p "drivers/$kernel"
cp "$work/usb_audio_source/"*.ko "drivers/$kernel/"
printf 'Built matching modules; private build retained at %s\n' "$work"

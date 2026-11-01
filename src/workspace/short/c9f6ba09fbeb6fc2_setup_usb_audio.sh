#!/bin/sh
# Load matching modules only; do not replace the kernel or install a service.
set -eu
cd /home/xilinx/tobii_z15
if [ -d /sys/bus/usb/drivers/snd-usb-audio ]; then exit 0; fi
if [ "$(id -u)" != 0 ]; then
    printf '%s\n' 'USB audio driver setup requires root' >&2
    exit 1
fi
if modprobe snd-usb-audio 2>/dev/null; then exit 0; fi
module_dir="drivers/$(uname -r)"
for name in snd-hwdep snd-rawmidi snd-usbmidi-lib snd-usb-audio; do
    module_name=$(printf '%s' "$name" | tr '-' '_')
    if [ ! -d "/sys/module/$module_name" ]; then
        if [ ! -f "$module_dir/$name.ko" ]; then
            printf 'No matching USB audio module: %s/%s.ko\n' "$module_dir" "$name" >&2
            exit 1
        fi
        insmod "$module_dir/$name.ko"
    fi
done

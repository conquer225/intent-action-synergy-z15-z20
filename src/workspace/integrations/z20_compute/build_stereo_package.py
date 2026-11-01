"""Assemble stereo runtime files without writing any removable device."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import tarfile
import time
import zlib

HERE = Path(__file__).resolve().parent
MODULES = ('__init__.py', 'video.py', 'stereo.py', 'stereo_capture.py', 'stereo_live.py', 'stereo_run.py')
LAUNCHER = b'''#!/bin/sh
set -eu
export PYTHONPATH=/opt/z20
device=
for candidate in /sys/class/uio/uio*; do
 [ -r "$candidate/name" ] || continue
 if [ "$(cat "$candidate/name")" = z20-video-observer ]; then
  [ -z "$device" ] || { echo "multiple video observers" >&2; exit 1; }
  device="/dev/$(basename "$candidate")"
 fi
done
[ -n "$device" ] || { echo "video observer absent; check matching BOOT and DTB" >&2; exit 1; }
exec /usr/bin/python3.7 -m z20_compute.stereo_run "$@" --device "$device"
'''
INIT = b'''#!/bin/sh
export PATH=/sbin:/bin:/usr/sbin:/usr/bin:/usr/local/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
echo Z20_STEREO_RAM_ROOT_READY
exec /sbin/init
'''
BOOT_COMMANDS = b'''echo Z20 stereo: retain running PL video, boot matched Linux
setenv bootargs console=ttyPS0,115200 earlycon rdinit=/init rw cma=64M clk_ignore_unused uio_pdrv_genirq.of_id=generic-uio
if fatload mmc 0:1 0x03000000 zImage; then
 if fatload mmc 0:1 0x02a00000 system.dtb; then
  if fatload mmc 0:1 0x10000000 rootfs.gz; then
   setenv stereo_ramdisk_size ${filesize}
   bootz 0x03000000 0x10000000:${stereo_ramdisk_size} 0x02a00000
  fi
 fi
fi
echo Z20_STEREO_BOOT_FAILED
'''


def script_image(commands, *, timestamp=0):
    payload = struct.pack('>II', len(commands), 0)+commands
    header = bytearray(struct.pack('>7I4B32s', 0x27051956, 0, timestamp, len(payload),
        0, 0, zlib.crc32(payload), 5, 2, 6, 0, b'Z20 stereo boot'))
    struct.pack_into('>I', header, 4, zlib.crc32(header))
    return bytes(header)+payload


def overlay_files():
    files = {'opt/z20/z20_compute/'+name:(HERE/'z20_compute'/name).read_bytes() for name in MODULES}
    files['usr/local/bin/z20-stereo'] = LAUNCHER
    return files


def build(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    boot_manifest = json.loads((args.boot/'manifest.json').read_text())
    if not boot_manifest.get('linux_handoff'):
        raise ValueError('BOOT must initialize video then hand off to U-Boot')
    actual_bit = hashlib.sha256((args.hardware/'system_wrapper.bit').read_bytes()).hexdigest()
    evidence_path=args.hardware/'manifest.json'
    if not evidence_path.is_file():
        raise ValueError('validated stereo hardware manifest is required')
    evidence=json.loads(evidence_path.read_text())
    if (not evidence.get('observer_netlist_present')
            or evidence.get('files',{}).get('system_wrapper.bit')!=actual_bit
            or any(evidence.get('sources',{}).get('hardware/rtl/'+name)!=
                   hashlib.sha256((HERE/'hardware/rtl'/name).read_bytes()).hexdigest()
                   for name in ('z20_video_epoch.sv','z20_video_observer.sv'))):
        raise ValueError('validated stereo hardware evidence does not match current sources/bitstream')
    if actual_bit != boot_manifest['files']['system.bit']:
        raise ValueError('BOOT and hardware bitstream differ')
    if boot_manifest.get('matched_xsa_sha256')!=evidence.get('files',{}).get('z20_stereo.xsa'):
        raise ValueError('BOOT and validated stereo XSA differ')
    boot = out/'boot';boot.mkdir(exist_ok=True)
    shutil.copyfile(args.boot/'BOOT.BIN', boot/'BOOT.BIN')
    shutil.copyfile(args.dtb, boot/'system.dtb')
    shutil.copyfile(args.kernel, boot/'zImage')
    (boot/'boot.scr').write_bytes(script_image(BOOT_COMMANDS))
    (boot/'boot.cmd').write_bytes(BOOT_COMMANDS)
    with tarfile.open(out/'runtime-overlay.tar.gz', 'w:gz') as archive:
        for name, data in overlay_files().items():
            item = tarfile.TarInfo(name);item.mode = 0o755 if name.startswith('usr/') else 0o644
            item.size=len(data);archive.addfile(item,io.BytesIO(data))
    inputs = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.dtb,args.kernel,args.boot/'BOOT.BIN']}
    (out/'manifest.json').write_text(json.dumps(dict(kind='stereo-linux-runtime',board_executed=False,
        inputs=inputs,files={name:hashlib.sha256((boot/name).read_bytes()).hexdigest()
            for name in ('BOOT.BIN','system.dtb','zImage','boot.scr','boot.cmd')}),indent=2))
    return out


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE/'build/stereo_release')
    parser.add_argument('--boot',type=Path,default=HERE/'build/stereo_linux_boot')
    parser.add_argument('--hardware',type=Path,default=HERE/'build/stereo_implementation')
    parser.add_argument('--dtb',type=Path,default=HERE/'build/linux_stage/z20-stereo.dtb')
    parser.add_argument('--kernel',type=Path,default=HERE/'build/official_linux/zynq_petalinux/4_linux_driver_boot/ready_to_test/zImage')
    print(build(parser.parse_args()))

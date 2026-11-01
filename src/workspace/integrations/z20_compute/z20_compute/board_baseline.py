"""Read-only inventory plus copies of the current boot/PL baseline on SD."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


def snapshot(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    report = dict(created_unix=time.time(), files={}, commands={})
    sources = [Path('/proc/config.gz'), Path('/sys/firmware/fdt')]
    sd = Path('/media/sd-mmcblk0p1/navigator-bringup')
    sources += [sd/name for name in ('zImage', 'system.bin', 'system.bit', 'camera-demo.dtb', 'system.dtb')]
    for source in sources:
        if not source.is_file():
            report['files'][str(source)] = dict(present=False)
            continue
        target = destination/source.name
        payload = source.read_bytes()
        target.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise IOError('baseline copy hash mismatch')
        report['files'][str(source)] = dict(present=True, copy=target.name, bytes=len(payload), sha256=digest)
    if (destination/'config.gz').is_file():
        (destination/'kernel.config').write_bytes(gzip.decompress((destination/'config.gz').read_bytes()))
    for name, args in [
        ('kernel', ['uname', '-a']), ('bootargs', ['cat', '/proc/cmdline']),
        ('network', ['ip', '-details', 'addr']), ('usb', ['lsusb']),
        ('mounts', ['cat', '/proc/mounts']), ('processes', ['ps', '-eo', 'pid,args']),
        ('modules', ['cat', '/proc/modules']), ('memory', ['cat', '/proc/meminfo'])]:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
        report['commands'][name] = dict(exit_code=result.returncode, output=result.stdout.decode(errors='replace'))
    report['uio'] = {p.name: (p/'name').read_text().strip() for p in Path('/sys/class/uio').glob('uio*')}
    path = destination/'baseline.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.destination), indent=2))


if __name__ == '__main__': main()

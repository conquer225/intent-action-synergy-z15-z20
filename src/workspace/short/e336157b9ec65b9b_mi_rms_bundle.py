"""Hash-guarded ARM-only integration/recovery. Never reload PL or reset the board."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

APP = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
CONFIG = Path('/etc/default/guardianloop-mi.json')
TEMPORARY = {
    '/run/systemd/system/guardianloop-cyton.service.d/90-mi-live-virtual.conf',
    '/run/systemd/system/guardianloop-cyton.service.d/95-mi-personal-study.conf',
    '/run/systemd/system/guardianloop-cyton.service.d/96-mi-rms-live-virtual.conf',
    '/run/systemd/system/guardianloop-web.service.d/90-mi-live-virtual.conf',
}
UNITS = ('guardianloop-cyton.service', 'guardianloop-web.service')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_state(bundle):
    ledger = json.loads((bundle/'transaction.json').read_text(encoding='utf-8'))
    for text, row in ledger['targets'].items():
        path = Path(text)
        if not (path.parent == APP or path == CONFIG or text in TEMPORARY):
            raise ValueError('Target outside the ARM integration scope: ' + text)
        if path.suffix in ('.bit', '.hwh') or path.name in ('BOOT.BIN', 'image.ub'):
            raise ValueError('PL and boot targets forbidden')
        for field, checksum in (('original', 'old_sha256'), ('replacement', 'new_sha256')):
            relative = row[field]
            if relative is not None:
                source = bundle/relative
                if source.resolve().parent not in ((bundle/'runtime').resolve(), (bundle/'config').resolve(),
                                                   (bundle/'rollback_original').resolve()):
                    raise ValueError('Invalid package path')
                if sha(source) != row[checksum]:
                    raise ValueError('Package checksum mismatch: ' + relative)
        actual = sha(path) if path.exists() else None
        permitted = {row['old_sha256'], row['new_sha256']}
        if text in TEMPORARY:
            permitted.add(None)  # /run is intentionally lost on reboot.
        if actual not in permitted:
            raise ValueError('Foreign board modification: ' + text)
    for text, expected in ledger['protected'].items():
        if text not in ledger['targets'] and sha(Path(text)) != expected:
            raise ValueError('Untouched board artifact changed: ' + text)
    for name, expected in ledger['runtime_sha256'].items():
        if Path(name).name != name or sha(bundle/'runtime'/name) != expected:
            raise ValueError('Runtime package checksum mismatch: ' + name)
    subprocess.run(['systemctl','is-active','--quiet','guardianloop-startup.service'], check=True)
    return ledger


def install(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['install','-m','644',str(source),str(target)], check=True)


def apply_files(bundle, ledger, rollback):
    withdrawn = bundle/('withdrawn-rollback' if rollback else 'withdrawn-overrides')
    withdrawn.mkdir(exist_ok=True)
    for ordinal, (text, row) in enumerate(ledger['targets'].items()):
        path = Path(text)
        source = row['original'] if rollback else row['replacement']
        if source is not None:
            install(bundle/source, path)
        elif path.exists():
            destination = withdrawn/(str(ordinal)+'-'+path.name)
            if destination.exists():
                raise ValueError('Prior withdrawal exists; inspect it before repeating')
            # /run overrides may be on tmpfs while the recovery bundle is on SD.
            shutil.move(str(path), str(destination))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check','install','rollback'))
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    ledger = read_state(bundle)
    if args.action == 'check':
        print('RMS_ARM_PACKAGE_CHECK_PASS: no writes, PL unchanged')
        return
    if os.geteuid() != 0:
        raise PermissionError('Explicit ARM change requires sudo')
    if args.action == 'install':
        for text, row in ledger['targets'].items():
            path = Path(text)
            if (sha(path) if path.exists() else None) != row['old_sha256']:
                raise ValueError('Install requires the exact pre-integration state: ' + text)
    startup = Path('/run/guardianloop-startup/status.json').read_bytes()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text()
    subprocess.run(['systemctl','stop',*UNITS], check=True)
    error = None
    try:
        apply_files(bundle, ledger, rollback=args.action == 'rollback')
        subprocess.run(['systemctl','daemon-reload'], check=True)
    except Exception as exc:
        error = exc
        if args.action == 'install':
            # Every original remains in the bundle, including the temporary overrides.
            apply_files(bundle, ledger, rollback=True)
            subprocess.run(['systemctl','daemon-reload'], check=True)
    finally:
        subprocess.run(['systemctl','start',*UNITS], check=True)
    if error is not None:
        raise error
    if (startup != Path('/run/guardianloop-startup/status.json').read_bytes()
            or boot != Path('/proc/sys/kernel/random/boot_id').read_text()):
        raise RuntimeError('Startup/boot unexpectedly changed')
    expected_key = 'old_sha256' if args.action == 'rollback' else 'new_sha256'
    for text, row in ledger['targets'].items():
        path = Path(text)
        if (sha(path) if path.exists() else None) != row[expected_key]:
            raise ValueError('Installed target mismatch: ' + text)
    report = dict(action=args.action, passed=True, pl_changed=False, boot_changed=False,
                  completed_monotonic=time.monotonic())
    (bundle/(args.action+'-result.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()

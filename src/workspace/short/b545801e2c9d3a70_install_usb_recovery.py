"""Board-local, backed-up installation of the serial-identity service fix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess


ROOT = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
STAGE = Path('/home/xilinx/gl-usb-recovery-20261007')
OVERRIDE = Path('/etc/systemd/system/guardianloop-cyton.service.d/40-usb-recovery.conf')
IDENTITY = Path('/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0')
SERVICE = 'guardianloop-cyton.service'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def systemctl(*args):
    subprocess.run(['systemctl', *args], check=True, timeout=35)


def restore(backup):
    if backup.parent != STAGE or not backup.name.startswith('backup-'):
        raise ValueError('Rollback must identify this installation backup')
    record = json.loads((backup/'installation.json').read_text())
    if record['override'] != str(OVERRIDE):
        raise ValueError('Rollback override differs')
    if OVERRIDE.exists() and sha(OVERRIDE) != record['override_sha256']:
        raise ValueError('Refusing to remove an override modified after this installation')
    systemctl('stop', SERVICE)
    for name in ('guardianloop_acquisition.py', 'release_manifest.json'):
        shutil.copy2(backup/name, ROOT/name)
    if OVERRIDE.exists():
        OVERRIDE.unlink()
    systemctl('daemon-reload')
    systemctl('start', SERVICE)
    print(json.dumps({'restored': str(backup)}), flush=True)


def install():
    if os.geteuid() != 0:
        raise PermissionError('Run the installer as root')
    if OVERRIDE.exists():
        raise FileExistsError('USB recovery override already exists; inspect before updating')
    manifest = json.loads((ROOT/'release_manifest.json').read_text())
    if not all(sha(ROOT/name) == digest for name, digest in manifest['files'].items()):
        raise ValueError('Formal release differs from its manifest')
    if not IDENTITY.is_char_device():
        raise FileNotFoundError('The accepted receiver identity is not present')
    backup = STAGE/('backup-'+secrets.token_hex(4))
    backup.mkdir(mode=0o700)
    for name in ('guardianloop_acquisition.py', 'release_manifest.json'):
        shutil.copy2(ROOT/name, backup/name)
    record = {'override': str(OVERRIDE), 'override_sha256': sha(STAGE/'guardianloop-cyton-usb.conf'),
              'receiver_identity': str(IDENTITY), 'previous_release': manifest['release_id']}
    (backup/'installation.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'backup': str(backup), 'receiver_node': str(IDENTITY.resolve())}), flush=True)
    systemctl('stop', SERVICE)
    try:
        incoming = ROOT/'guardianloop_acquisition.py.usb-new'
        shutil.copyfile(STAGE/'guardianloop_acquisition.py', incoming)
        os.chmod(incoming, 0o644)
        os.replace(incoming, ROOT/'guardianloop_acquisition.py')
        shutil.copyfile(STAGE/'guardianloop-cyton-usb.conf', OVERRIDE)
        os.chmod(OVERRIDE, 0o644)
        manifest['previous_release_id'] = manifest['release_id']
        manifest['release_id'] = 'guardianloop-fixed8-usb-recovery-20261007'
        manifest['files']['guardianloop_acquisition.py'] = sha(ROOT/'guardianloop_acquisition.py')
        manifest['usb_recovery'] = {
            'serial_identity': str(IDENTITY), 'restart_owner': 'systemd',
            'wait_without_receiver': True, 'models_changed': False,
            'physical_usb_stability_verified': False,
            'service_override': str(OVERRIDE), 'service_override_sha256': sha(OVERRIDE),
        }
        incoming = ROOT/'release_manifest.json.usb-new'
        incoming.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        os.chmod(incoming, 0o644)
        os.replace(incoming, ROOT/'release_manifest.json')
        systemctl('daemon-reload')
        systemctl('start', SERVICE)
    except BaseException:
        restore(backup)
        raise
    print('USB_IDENTITY_RECOVERY_INSTALLED', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    if args.rollback is None:
        install()
    else:
        restore(args.rollback)

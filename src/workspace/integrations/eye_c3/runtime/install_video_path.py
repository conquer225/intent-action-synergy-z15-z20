"""Replace only the tested display payload after its owner has released DMA."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

DISPLAY = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')
FILES = ('media_player.py', 'system_hdmi.py', 'frame_fitter.so',
         'menu-shells-portrait-live.npz')
SERVICES = ('guardianloop-cyton.service', 'guardianloop-web.service')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Expected an ordinary file: ' + str(path))


def services():
    return subprocess.run(['systemctl', 'show', *SERVICES, '-p', 'Id',
        '-p', 'MainPID', '-p', 'NRestarts', '-p', 'ActiveState'],
        check=True, capture_output=True, text=True, timeout=10).stdout


def protected():
    state = json.loads((DISPLAY / 'state.json').read_text())
    media = json.loads((DISPLAY / 'media_state.json').read_text())
    if media.get('user_controlled') is not True:
        raise ValueError('This update requires the existing user-controlled entry')
    formal = Path(state['formal_entry']).parent
    hashes = {str(formal / n): h for n, h in state['formal_hashes'].items()}
    hashes[str(formal / 'release_manifest.json')] = digest(formal / 'release_manifest.json')
    hashes.update(media['hardware_hashes'])
    hashes[media['native_scan_library']] = media['native_scan_sha256']
    for p, h in hashes.items():
        if digest(Path(p)) != h:
            raise ValueError('Protected file differs: ' + p)
    return dict(boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                services=services(), hashes=hashes)


def assert_stopped():
    current = json.loads((DISPLAY / 'player_status.json').read_text())
    ident = current['session_id']
    if not re.fullmatch('play-[a-f0-9]{8}', ident):
        raise ValueError('Unknown display owner')
    pid = subprocess.run(['systemctl', 'show', ident + '.service', '-p',
        'MainPID', '--value'], check=True, capture_output=True, text=True,
        timeout=10).stdout.strip()
    report = json.loads((DISPLAY / (ident + '-report.json')).read_text())
    if (pid != '0' or report.get('errors') or not all(report.get(k) is True
            for k in ('display_halted', 'buffers_released', 'original_restored'))):
        raise ValueError('Display cleanup has not passed; no file replacement')
    from pynq import PL
    media = json.loads((DISPLAY / 'media_state.json').read_text())
    if PL.bitfile_name != media['original_overlay']:
        raise ValueError('Original overlay has not been restored')
    return ident


def replace(path, data, mode, uid, gid):
    temporary = path.with_name(path.name + '.video-update-' + str(os.getpid()))
    with temporary.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, mode)
    os.chown(temporary, uid, gid)
    os.replace(temporary, path)


def prepare(candidate):
    expected = json.loads((candidate / 'candidate-hashes.json').read_text())
    before = protected()
    pins_path = DISPLAY / 'boot-pins.json'
    pins = json.loads(pins_path.read_text())
    for p, h in pins['files'].items():
        if digest(Path(p)) != h:
            raise ValueError('Existing boot pin differs: ' + p)
    for name in FILES:
        regular(candidate / name)
        if digest(candidate / name) != expected[name]:
            raise ValueError('Tested payload changed: ' + name)
        regular(DISPLAY / name)
        pins['files'][str(DISPLAY / name)] = expected[name]
    regular(pins_path)
    backup = candidate / 'active-backup'
    backup.mkdir(mode=0o700)
    rows = []
    for name in (*FILES, 'boot-pins.json'):
        path = DISPLAY / name
        info = path.stat()
        shutil.copy2(path, backup / name)
        old_sha = digest(path)
        if digest(backup / name) != old_sha:
            raise ValueError('Backup verification failed: ' + name)
        if name == 'boot-pins.json':
            data = json.dumps(pins, indent=2).encode()
            (candidate / 'new-boot-pins.json').write_bytes(data)
            source = candidate / 'new-boot-pins.json'
        else:
            source = candidate / name
        rows.append(dict(name=name, old_sha=old_sha, new_sha=digest(source),
                         mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid))
    plan = dict(before=before, files=rows)
    with (candidate / 'display-update-plan.json').open('x') as stream:
        json.dump(plan, stream, indent=2)
    return dict(prepared=True, backup=str(backup), protected_files=len(before['hashes']), files=rows)


def operate(candidate, rollback=False):
    plan = json.loads((candidate / 'display-update-plan.json').read_text())
    owner = assert_stopped()
    if protected() != plan['before']:
        raise ValueError('Acquisition, boot, model or hardware state changed')
    rows = plan['files']
    if tuple(row['name'] for row in rows) != (*FILES, 'boot-pins.json'):
        raise ValueError('Unexpected display update scope')
    payloads = []
    for row in rows:
        name = row['name']
        source = candidate / 'active-backup' / name if rollback else (
            candidate / ('new-boot-pins.json' if name == 'boot-pins.json' else name))
        regular(source)
        regular(DISPLAY / name)
        target_sha = row['old_sha'] if rollback else row['new_sha']
        if digest(source) != target_sha or digest(DISPLAY / name) != (
                row['new_sha'] if rollback else row['old_sha']):
            raise ValueError('Concurrent or unverified change: ' + name)
        payloads.append((row, source.read_bytes()))
    written = []
    try:
        for row, data in payloads:
            replace(DISPLAY / row['name'], data, row['mode'], row['uid'], row['gid'])
            written.append(row)
            if digest(DISPLAY / row['name']) != (row['old_sha'] if rollback else row['new_sha']):
                raise ValueError('Installed checksum differs')
    except Exception:
        if not rollback:
            for row in reversed(written):
                if digest(DISPLAY / row['name']) != row['new_sha']:
                    raise ValueError('Concurrent update prevents automatic rollback')
                replace(DISPLAY / row['name'], (candidate / 'active-backup' / row['name']).read_bytes(),
                        row['mode'], row['uid'], row['gid'])
        raise
    return dict(installed=not rollback, rolled_back=rollback, stopped_owner=owner,
                protected_unchanged=protected() == plan['before'],
                hashes={row['name']: digest(DISPLAY / row['name']) for row in rows})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'install', 'rollback', 'audit'))
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    if candidate.parent != Path('/home/xilinx') or not re.fullmatch('gl-video-path-20261009-[A-Za-z0-9]{6}', candidate.name):
        raise ValueError('Foreign candidate directory')
    if args.action == 'prepare':
        result = prepare(candidate)
    elif args.action == 'audit':
        plan = json.loads((candidate / 'display-update-plan.json').read_text())
        pins = json.loads((DISPLAY / 'boot-pins.json').read_text())
        result = dict(protected_unchanged=protected() == plan['before'],
            pin_mismatches=[p for p, h in pins['files'].items() if digest(Path(p)) != h],
            hashes={name: digest(DISPLAY / name) for name in FILES})
    else:
        result = operate(candidate, rollback=args.action == 'rollback')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

"""Install the verified audio display, with an exact previous-session rollback."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parent
LIVE = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')


def run(*args, timeout=25):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT,
                                   timeout=timeout).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix+'.audio-new')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.chmod(0o600)
    temporary.replace(path)


def same_boot(plan):
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != plan['boot']:
        raise RuntimeError('Boot changed; do not adopt an old installation transaction')


def pid(unit):
    return int(run('systemctl', 'show', unit, '-p', 'MainPID', '--value') or 0)


def stop_services(plan):
    # Stop the observer before publishing a new owner for the same session.
    for record in reversed(plan['services']):
        run('systemctl', 'stop', '--no-block', record['unit'])
        deadline = time.monotonic()+25
        while pid(record['unit']):
            if time.monotonic() > deadline:
                raise RuntimeError('Owner did not stop cleanly: '+record['unit'])
            time.sleep(.2)
    from pynq import PL
    if PL.bitfile_name != plan['original_overlay']:
        raise RuntimeError('Previous display has not restored the formal PL')
    report = json.loads((LIVE/(plan['session_id']+'-report.json')).read_text())
    if not (report.get('original_restored') and report.get('buffers_released')):
        raise RuntimeError('Display cleanup did not release its DMA buffers')


def start_services(plan, audio):
    config = json.loads(Path(plan['player_state']).read_text())
    status_paths = [LIVE/'player_status.json',
                    Path('/dev/shm')/(LIVE.name+'-player-status.json')]
    for path in status_paths:
        save(path, dict(state='starting', session_id=config['session_id'],
                        silent=not audio, updated_monotonic=time.monotonic()))
    for index, record in enumerate(plan['services']):
        unit = record['unit']
        if run('systemctl', 'show', unit, '-p', 'LoadState', '--value') == 'not-found':
            command = ['systemd-run', '--unit='+unit]
            command += ['--property='+key+'='+value
                        for key, value in record['properties'].items()]
            run(*command, *record['argv'])
        else:
            run('systemctl', 'start', unit)
        if index == 0:
            deadline = time.monotonic()+65
            while True:
                row = json.loads(status_paths[1].read_text())
                if (row.get('session_id') == config['session_id']
                        and row.get('state') in ('menu', 'playing')
                        and time.monotonic()-row['updated_monotonic'] < 2):
                    if audio and not (row.get('audio_output') and row.get('audio', {}).get('volume_percent') == 40):
                        raise RuntimeError('New display is ready but audio contract differs: '+str(row.get('audio')))
                    break
                if not pid(unit) or time.monotonic() > deadline:
                    raise RuntimeError('Display did not publish its ready state: '+str(row))
                time.sleep(.25)
    time.sleep(3)
    if any(not pid(record['unit']) for record in plan['services']):
        raise RuntimeError('A restored service exited after startup')
    row = json.loads(status_paths[1].read_text())
    if time.monotonic()-row['updated_monotonic'] > 2:
        raise RuntimeError('Display heartbeat expired after observer startup')
    return row


def rollback(plan):
    same_boot(plan)
    stop_services(plan)
    for row in plan['files']:
        target = Path(row['target'])
        if row['old_sha'] is None:
            # These exact helper files did not exist before this transaction.
            if target.exists():
                if digest(target) != row['new_sha']:
                    raise RuntimeError('Refuse to remove an externally modified helper')
                target.unlink()
        else:
            backup = ROOT/'backup'/row['key']
            if digest(backup) != row['old_sha']:
                raise RuntimeError('Backup checksum differs')
            shutil.copy2(backup, target)
    row = start_services(plan, audio=False)
    save(ROOT/'rollback.json', dict(restored=True, player=row,
                                  acquisition_pid=pid('guardianloop-cyton.service')))


def install(plan):
    same_boot(plan)
    for row in plan['files']:
        target = Path(row['target'])
        actual = digest(target) if target.exists() else None
        if actual != row['old_sha'] or digest(ROOT/'payload'/row['key']) != row['new_sha']:
            raise RuntimeError('Install precondition changed: '+str(target))
    for path, expected in plan['artifacts'].items():
        if digest(Path(path)) != expected:
            raise RuntimeError('Verified hardware/audio artifact changed: '+path)
    (ROOT/'backup').mkdir(exist_ok=False)
    for row in plan['files']:
        if row['old_sha'] is not None:
            shutil.copy2(row['target'], ROOT/'backup'/row['key'])
    save(ROOT/'backup-ready.json', dict(ready=True, boot=plan['boot']))
    try:
        stop_services(plan)
        for row in plan['files']:
            target = Path(row['target'])
            pending = target.with_suffix(target.suffix+'.audio-install')
            shutil.copyfile(ROOT/'payload'/row['key'], pending)
            pending.chmod(row['mode'])
            os.replace(pending, target)
        row = start_services(plan, audio=True)
        if pid('guardianloop-cyton.service') != plan['acquisition_pid']:
            raise RuntimeError('Acquisition restarted during display-only installation')
        from pynq import PL
        if PL.bitfile_name != plan['display_overlay']:
            raise RuntimeError('Loaded display differs from installed candidate')
        save(ROOT/'installed.json', dict(installed=True, player=row,
             display_overlay=PL.bitfile_name, acquisition_pid=plan['acquisition_pid'],
             motors_commanded=False, boot_image_modified=False))
        run('systemctl', 'stop', plan['rollback_timer']+'.timer')
    except Exception as error:
        save(ROOT/'failure.json', dict(error=str(error)))
        rollback(plan)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'rollback'))
    args = parser.parse_args()
    plan = json.loads((ROOT/'plan.json').read_text())
    with (ROOT/'transaction.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'install':
            install(plan)
        elif not (ROOT/'installed.json').exists() and (ROOT/'backup-ready.json').exists():
            rollback(plan)


if __name__ == '__main__':
    main()

"""Own one volatile ARM override; recover its exact display before restarting ARM."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import signal
import threading
import time

from playback_policy import recovery_reason

BASE = Path(__file__).resolve().parent
SERVICE = 'guardianloop-cyton.service'
OVERRIDE = Path('/run/systemd/system/guardianloop-cyton.service.d/90-guardianloop-hdmi-test.conf')
PYTHON = '/usr/local/share/pynq-venv/bin/python3'


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=55).stdout.strip()


def save(state, name, value):
    path = BASE / name
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    os.replace(temporary, path)


def load(path):
    if path.resolve().parent != BASE:
        raise ValueError('Foreign isolated state')
    state = json.loads(path.read_text())
    if state['remote'] != str(BASE) or not re.fullmatch('gl-hdmi-live-20261008-[a-f0-9]{8}', BASE.name):
        raise ValueError('Unexpected isolated target')
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != state['boot']:
        raise ValueError('Boot changed; refuse this old session')
    return state


def restore(state):
    if state.get('user_controlled') is True:
        guard = BASE.name + '-watch.service'
        if run('systemctl', 'show', guard, '-p', 'LoadState', '--value') != 'not-found':
            run('systemctl', 'stop', guard)
    with (BASE / 'session_restore.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if OVERRIDE.exists() and OVERRIDE.read_text() != state['override_text']:
            raise ValueError('Another owner changed the temporary override')
        status_path = BASE / 'player_status.json'
        if status_path.is_file():
            player = json.loads(status_path.read_text())
            session = player.get('session_id', '')
            if not re.fullmatch('play-[a-f0-9]{8}', session):
                raise ValueError('Unrecognized private display session')
            run('env', 'XILINX_XRT=/usr', PYTHON, str(BASE / 'playback_recovery.py'),
                '--state', str(BASE / (session + '.json')))
        server = BASE.name + '-server.service'
        loaded = run('systemctl', 'show', server, '-p', 'LoadState', '--value')
        if loaded != 'not-found':
            run('systemctl', 'stop', server)
        restarted = False
        if OVERRIDE.exists():
            # The exact recoverable text remains in state.json; no /etc files change.
            OVERRIDE.unlink()
            run('systemctl', 'daemon-reload')
            run('systemctl', 'restart', SERVICE)
            restarted = True
        save(state, 'restoration.json', dict(override_removed=not OVERRIDE.exists(),
            formal_acquisition_restarted=restarted,
            services=run('systemctl', 'show', SERVICE, '-p', 'MainPID', '-p', 'ActiveState'),
            formal_files_modified=False))
        print('VOLATILE_HDMI_BACKEND_RESTORED', flush=True)


def watch(state):
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    latest = recovered = None
    started = time.monotonic()
    while not stopped.wait(2):
        disk = BASE / 'player_status.json'
        if not disk.exists():
            continue
        row = json.loads(disk.read_text())
        session = row.get('session_id', '')
        if not re.fullmatch('play-[a-f0-9]{8}', session):
            raise ValueError('Watch refuses an unrecognized display session')
        if session != latest:
            latest, started = session, time.monotonic()
        if session == recovered:
            continue
        ram = Path('/dev/shm') / (BASE.name + '-player-status.json')
        if ram.exists():
            live = json.loads(ram.read_text())
            if live.get('session_id') == session:
                row = live
        active = int(run('systemctl', 'show', session + '.service', '-p', 'MainPID', '--value') or 0) > 0
        reason = recovery_reason(active, row, time.monotonic(), started)
        if reason is None:
            continue
        report = BASE / (session + '-report.json')
        result = json.loads(report.read_text()) if report.exists() else {}
        if not active and result.get('original_restored') and result.get('buffers_released'):
            recovered = session
            continue
        run('env', 'XILINX_XRT=/usr', PYTHON, str(BASE / 'playback_recovery.py'),
            '--state', str(BASE / (session + '.json')))
        save(state, 'fault_recovery.json', dict(session=session, reason=reason,
            webpage_left_open=True, fixed_expiry=False))
        recovered = session


def activate(state, path):
    if (BASE / 'activated.json').exists() or OVERRIDE.exists():
        raise ValueError('Temporary override already exists; inspect or restore')
    if run('systemctl', 'show', SERVICE, '-p', 'MainPID', '--value') != str(state['before_pid']):
        raise ValueError('Acquisition changed after preflight')
    # A local Ethernet/AP connection is sufficient; Internet/SSID is irrelevant.
    addresses = json.loads(run('ip', '-j', '-4', 'addr', 'show', 'up'))
    if not any(a.get('scope') == 'global' for interface in addresses
               for a in interface.get('addr_info', [])):
        raise ValueError('No active local IPv4 interface; connect Ethernet or the board AP')
    user_controlled = state.get('user_controlled') is True
    if user_controlled:
        recovery = Path('/run/systemd/system') / (BASE.name + '-recover.service')
        with recovery.open('x') as handle:
            handle.write('[Unit]\nDescription=GuardianLoop fault-only recovery\n[Service]\nType=oneshot\n'
                'Environment=XILINX_XRT=/usr\nExecStart=' + PYTHON + ' ' +
                str(BASE / 'hdmi_live_session.py') + ' restore --state ' + str(path) + '\n')
        run('systemctl', 'daemon-reload')
    else:
        run('systemd-run', '--unit=' + BASE.name + '-recover', '--on-active=600s',
            '--timer-property=AccuracySec=1s', 'env', 'XILINX_XRT=/usr', PYTHON,
            str(BASE / 'hdmi_live_session.py'), 'restore', '--state', str(path))
    try:
        OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
        with OVERRIDE.open('x') as handle:
            handle.write(state['override_text'])
        run('chmod', '600', str(OVERRIDE))
        run('systemctl', 'daemon-reload')
        run('systemctl', 'restart', SERVICE)
        if user_controlled:
            run('systemd-run', '--unit=' + BASE.name + '-watch',
                '--property=OnFailure=' + BASE.name + '-recover.service',
                '--property=KillMode=process', '--property=TimeoutStopSec=infinity',
                'env', 'XILINX_XRT=/usr', PYTHON, str(BASE / 'hdmi_live_session.py'),
                'watch', '--state', str(path))
        lifetime = [] if user_controlled else ['--property=RuntimeMaxSec=570s']
        run('systemd-run', '--unit=' + BASE.name + '-server', *lifetime,
            '--property=TimeoutStopSec=10s',
            '--property=MemoryMax=384M', '--property=Nice=5', '--property=LimitCORE=0',
            'env', 'XILINX_XRT=/usr', 'OPENBLAS_NUM_THREADS=1', PYTHON,
            str(BASE / 'media_server.py'), '--key-file', str(BASE / 'access.key'), '--port', '9119')
        save(state, 'activated.json', dict(timer_seconds=None if user_controlled else 600,
            display_seconds=None if user_controlled else 480, user_controlled=user_controlled,
            new_pid=run('systemctl', 'show', SERVICE, '-p', 'MainPID', '--value'),
            visible_flash_started=False, physical_output_enabled=False))
        print('USER_CONTROLLED_HDMI_ACTIVATED_NO_EXPIRY_NO_FLICKER' if user_controlled else
              'TEMPORARY_HDMI_BACKEND_ACTIVATED_WITH_RECOVERY_NO_FLICKER', flush=True)
    except Exception:
        restore(state)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('activate', 'restore', 'watch'))
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    state = load(args.state)
    if args.action == 'activate':
        activate(state, args.state.resolve())
    elif args.action == 'restore':
        restore(state)
    else:
        watch(state)


if __name__ == '__main__':
    main()

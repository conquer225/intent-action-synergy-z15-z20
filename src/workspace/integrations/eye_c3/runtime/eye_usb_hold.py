"""Finite eye USB diagnostic; no calibration, control, or PL programming."""
import argparse
from contextlib import nullcontext
import fcntl
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from pynq import PL
from upload_server import write_json

BASE = Path(__file__).resolve().parent
EYE_ROOT = Path('/home/xilinx/brain_eye_coexist_20261005/eye')
ORIGINAL = '/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.bit'
DISPLAY = '/home/xilinx/tobii_z15/overlay/eye_wifi.bit'
sys.path.insert(0, str(EYE_ROOT / 'src'))
from calibration_worker import Worker
from coexist_guard import CoexistGuard


def interrupted(*_):
    raise KeyboardInterrupt


def usb_state():
    device = Path('/sys/bus/usb/devices/1-1.2')
    fields = ('idVendor', 'idProduct', 'devnum', 'power/control',
              'power/runtime_status', 'power/runtime_suspended_time')
    result = {}
    for field in fields:
        try:
            result[field] = (device / field).read_text().strip()
        except FileNotFoundError:
            result[field] = None
    return result


def check_sample_freshness(last_sample, now, started):
    if last_sample is None:
        if now-started > 10:
            raise RuntimeError('Native sampler produced no samples within 10 seconds')
    elif now-last_sample > 3:
        raise RuntimeError('Native stream silent for more than 3 seconds')


def display_owner(unit, page, expected_pid=None):
    if not re.fullmatch(r'eye-usb-(menu|video)-20261007-\d+\.service', unit):
        raise ValueError('Unexpected display unit')
    fields = dict(line.split('=', 1) for line in subprocess.check_output(
        ['systemctl', 'show', unit, '-p', 'MainPID', '-p', 'ActiveState'],
        text=True, timeout=3).splitlines())
    pid = int(fields['MainPID'])
    if fields['ActiveState'] != 'active' or pid <= 0 or (expected_pid and pid != expected_pid):
        raise RuntimeError('Display owner stopped or changed')
    argv = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
    state_path = BASE / (unit[:-8] + '.json')
    if str(BASE/'media_player.py').encode() not in argv or str(state_path).encode() not in argv:
        raise RuntimeError('Display process does not match this diagnostic')
    status = json.loads((Path('/dev/shm')/(BASE.name+'-player-status.json')).read_text())
    if (status['session_id'] != unit[:-8] or status['state'] not in ('playing', 'menu') or
            time.monotonic()-status['updated_monotonic'] > 2 or status['system']['eye'] or
            status['system']['page'] != page or status['system']['physical_output_enabled']):
        raise RuntimeError('Display status is not the expected non-controlling diagnostic')
    return pid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='eye-usb-original-pl-20261007')
    parser.add_argument('--hdmi-owner')
    parser.add_argument('--page', choices=('home', 'video'))
    args = parser.parse_args()
    if not re.fullmatch(r'eye-usb-[a-z0-9-]{1,64}', args.label):
        raise ValueError('Invalid diagnostic label')
    if bool(args.hdmi_owner) != bool(args.page):
        raise ValueError('Shared display requires its unit and page')
    report_path = BASE / (args.label+'-report.json')
    progress_path = BASE / (args.label+'-progress.json')
    if report_path.exists() or progress_path.exists():
        raise RuntimeError('Do not replace diagnostic evidence')
    report = dict(physical_control=False, calibration_requested=False,
                  hdmi_started=bool(args.hdmi_owner), page=args.page, seconds_planned=140, errors=[],
                  messages=0, quality_messages=0, usb_observations=[])
    worker = None
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    context = nullcontext() if args.hdmi_owner else open('/run/lock/guardianloop-pl.lock', 'a')
    with context as lock:
        if lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        expected_pl = DISPLAY if args.hdmi_owner else ORIGINAL
        owner_pid = display_owner(args.hdmi_owner, args.page) if args.hdmi_owner else None
        if PL.bitfile_name != expected_pl:
            raise RuntimeError('Expected diagnostic PL is not already loaded')
        guard = CoexistGuard(EYE_ROOT, ORIGINAL)
        report['admission'] = guard.verify()
        report.update(expected_pl=expected_pl, hdmi_owner_pid=owner_pid)
        start = time.monotonic()
        last_observation = -1.
        last_sample = None
        try:
            worker = Worker(EYE_ROOT, 220, 160, selection_test=True, relative=True)
            report.update(worker_pid=worker.process.pid,
                          capture_directory=str(worker.directory))
            while time.monotonic() - start < 140:
                now = time.monotonic()
                for event in worker.poll():
                    report['messages'] += 1
                    if event.get('kind') in ('quality', 'direction_gaze', 'horizontal_gaze', 'gaze'):
                        last_sample = now
                    if event.get('kind') == 'quality':
                        report['quality_messages'] += 1
                    if event.get('kind') == 'error':
                        report['errors'].append(event)
                if worker.done:
                    report['early_native_exit'] = worker.process.returncode
                    raise RuntimeError('Native sampler exited before diagnostic completed')
                check_sample_freshness(last_sample, now, start)
                if now - last_observation >= 5:
                    guard.check_runtime()
                    if args.hdmi_owner:
                        display_owner(args.hdmi_owner, args.page, owner_pid)
                    if PL.bitfile_name != expected_pl:
                        raise RuntimeError('Unexpected PL change')
                    report['usb_observations'].append(dict(elapsed_s=now-start,
                        last_sample_age_s=now-last_sample if last_sample is not None else None,
                        messages=report['messages'], quality_messages=report['quality_messages'], **usb_state()))
                    write_json(progress_path, dict(elapsed_s=now-start,
                        messages=report['messages'], quality_messages=report['quality_messages'],
                        last_sample_age_s=now-last_sample if last_sample is not None else None,
                        worker_pid=worker.process.pid, usb=usb_state()))
                    last_observation = now
                time.sleep(.05)
            report['full_interval_completed'] = time.monotonic()-start >= 140 and not worker.done and last_sample is not None
            guard.check_runtime()
        except KeyboardInterrupt:
            report['interrupted'] = True
        except Exception as error:
            report['errors'].append(dict(type=type(error).__name__, detail=str(error)))
            raise
        finally:
            report['wall_s'] = time.monotonic()-start
            report['last_sample_age_s'] = time.monotonic()-last_sample if last_sample is not None else None
            if worker:
                if worker.process.poll() is None:
                    try:
                        worker.command('stop')
                        until = time.monotonic()+3
                        while worker.process.poll() is None and time.monotonic() < until:
                            worker.poll()
                            time.sleep(.05)
                    except (BrokenPipeError, RuntimeError) as error:
                        report['stop_command_error'] = str(error)
                worker.close()
                report['native_cleanup_exit'] = worker.process.returncode
            report['expected_pl_unchanged'] = PL.bitfile_name == expected_pl
            report['original_pl_unchanged'] = PL.bitfile_name == ORIGINAL
            report['final_usb'] = usb_state()
            write_json(report_path, report)
    print(json.dumps({key: report[key] for key in ('wall_s', 'messages', 'quality_messages',
        'errors', 'original_pl_unchanged')}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()

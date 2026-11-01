"""Finite authorized HDMI coexistence test; original services are never stopped."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import fcntl
import os
import signal

BRAIN = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
EYE_ORIGINAL = Path('/home/xilinx/tobii_z15')
CANDIDATE = Path('/home/xilinx/brain_eye_coexist_20261005/eye')
sys.path.insert(0, str(CANDIDATE / 'src'))
from coexist_guard import CoexistGuard


def protected_hashes():
    manifest = json.loads((BRAIN / 'release_manifest.json').read_text())
    paths = [BRAIN / name for name in manifest['files']] + [BRAIN / 'release_manifest.json']
    paths += list((EYE_ORIGINAL / 'src').glob('*'))
    paths += [EYE_ORIGINAL / name for name in ('display_session.sh', 'start_local_media.sh',
              'is4-calibration', 'libtobii_display.so', 'overlay/eye_wifi.bit', 'overlay/eye_wifi.hwh')]
    paths += [Path('/etc/systemd/system') / name for name in (
        'guardianloop-cyton.service', 'guardianloop-web.service', 'guardianloop-startup.service')]
    paths += list(Path('/etc/systemd/system/guardianloop-cyton.service.d').glob('*.conf'))
    paths += list(Path('/etc/systemd/system/guardianloop-web.service.d').glob('*.conf'))
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}


def services():
    data = subprocess.check_output(['systemctl', 'show', 'guardianloop-cyton.service',
                                    'guardianloop-web.service', '-p', 'Id', '-p', 'ActiveState',
                                    '-p', 'MainPID', '-p', 'NRestarts'], text=True, timeout=3)
    result = {}
    for block in data.strip().split('\n\n'):
        fields = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
        result[fields.pop('Id')] = fields
    return result


def sample(phase):
    row = {'phase': phase, 'monotonic_s': time.monotonic(), 'services': services()}
    for key, path in (('primary', '/run/guardianloop/status.json'),
                      ('telemetry', '/run/guardianloop/telemetry.json')):
        try:
            value = json.loads(Path(path).read_text())
        except (FileNotFoundError, json.JSONDecodeError) as error:
            row[key] = {'read_error': str(error)}
            continue
        if key == 'primary':
            row[key] = {name: value.get(name) for name in (
                'packets_seen', 'dropped_packets', 'sequence_gaps', 'state', 'valid',
                'filter_backend', 'input_age_at_prediction_seconds', 'calibration_current',
                'calibration_total', 'last_inference_window')}
            row[key]['emotion_state'] = (value.get('emotion') or {}).get('state')
        else:
            row[key] = {name: value.get(name) for name in (
                'packets_seen', 'dropped_packets', 'sequence_gaps', 'sample_index', 'runtime')}
    started = time.monotonic()
    try:
        with urllib.request.urlopen('http://127.0.0.1:9102/', timeout=2) as response:
            row['web'] = {'code': response.status, 'bytes': len(response.read())}
    except OSError as error:
        row['web'] = {'error': str(error)}
    row['web']['wall_ms'] = (time.monotonic() - started) * 1000
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--locate', action='store_true')
    parser.add_argument('--media', action='store_true')
    parser.add_argument('--shared-pl', action='store_true')
    parser.add_argument('--stop-after', type=int, help='Earliest candidate termination time; also wait for HDMI/USB readiness logs')
    parser.add_argument('--direct-framebuffer', action='store_true')
    parser.add_argument('--software-only', action='store_true')
    args = parser.parse_args()
    if args.stop_after is not None and not 1 <= args.stop_after < args.seconds:
        raise ValueError('Candidate stop time must be within the finite session')
    if args.direct_framebuffer and not args.media:
        raise ValueError('Direct framebuffer comparison requires the media test')
    args.output.mkdir(parents=True, exist_ok=False)
    if args.software_only:
        before, hashes = services(), protected_hashes()
        started = time.monotonic()
        tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s',
                                str(CANDIDATE / 'tests'), '-p', 'test_*.py'],
                               capture_output=True, text=True, timeout=300)
        report = {'tests_exit_code': tests.returncode, 'tests': tests.stdout + tests.stderr,
                  'elapsed_s': time.monotonic() - started, 'services_before': before,
                  'services_after': services(), 'protected_files_unchanged': protected_hashes() == hashes,
                  'pl_programmed_by_test': False}
        report['services_unchanged'] = report['services_after'] == before
        (args.output / 'software_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(report['tests'], flush=True)
        if tests.returncode or not report['services_unchanged'] or not report['protected_files_unchanged']:
            raise RuntimeError('Board software regression failed')
        return
    from pynq import PL, Overlay
    original = PL.bitfile_name
    report = {'original_pl': original, 'protected_before': protected_hashes(),
              'services_before': services(), 'admission': CoexistGuard(CANDIDATE, original).verify(),
              'eye_seconds': args.seconds, 'locate': args.locate, 'media': args.media,
              'shared_pl': args.shared_pl, 'samples': [],
              'pl_switch_authorized': True, 'startup_changed': False}
    child = None
    log = None
    pl_lock = None
    shared_loaded = False
    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        for _ in range(8):
            report['samples'].append(sample('before'))
            time.sleep(2)
        if args.shared_pl:
            pl_lock = open('/run/lock/guardianloop-pl.lock', 'a')
            fcntl.flock(pl_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            report['shared_load_started_s'] = time.monotonic()
            shared_loaded = True
            # A constructor failure may occur after programming the fabric.
            Overlay(str(CANDIDATE / 'overlay/eye_wifi.bit'))
            lease = {'owner_pid': os.getpid(), 'boot_id': report['admission']['boot_id'],
                     'bitfile': PL.bitfile_name, 'recovery': original}
            (CANDIDATE / 'shared_pl.json').write_text(json.dumps(lease))
            report['shared_load_completed_s'] = time.monotonic()
            for _ in range(6):
                report['samples'].append(sample('shared_pl_warmup'))
                time.sleep(2)
        command = [sys.executable, '-u', str(CANDIDATE / 'src/hdmi_guide.py'), '--coexist',
                   '--coexist-seconds', str(args.seconds), '--local-media',
                   '--media-dir', str(EYE_ORIGINAL / 'media'),
                   '--control-dir', '/dev/shm/brain_eye_coexist/' + args.output.name]
        if args.locate:command.append('--coexist-locate')
        if args.media:
            command = [sys.executable, '-u', str(CANDIDATE / 'tools/check_local_media_board.py'),
                       '--hdmi', '--coexist', '--samples', str(EYE_ORIGINAL / 'media_smoke')]
        if args.shared_pl:command.append('--shared-pl')
        if args.direct_framebuffer:command.append('--direct-framebuffer')
        log = (args.output / 'eye.log').open('w')
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        child_started = time.monotonic()
        deadline = child_started + args.seconds + 45
        while child.poll() is None:
            report['samples'].append(sample('eye_running'))
            if args.stop_after is not None and not report.get('candidate_stop_sent_s') and time.monotonic() - child_started >= args.stop_after:
                progress = (args.output / 'eye.log').read_text()
                ready = 'phase=' in progress and (not args.locate or '"stage": "locate"' in progress)
                if ready:
                    report['candidate_stop_ready_confirmed'] = True
                    report['candidate_stop_sent_s'] = time.monotonic()
                    child.terminate()
            if time.monotonic() > deadline:
                raise TimeoutError('Eye candidate exceeded its finite deadline')
            if services() != report['services_before']:
                raise RuntimeError('Original brain/web service changed during coexistence')
            time.sleep(2)
        report['eye_exit_code'] = child.returncode
        if args.stop_after is not None and not report.get('candidate_stop_ready_confirmed'):
            raise RuntimeError('Candidate did not reach the runtime termination test')
        if args.shared_pl:
            for _ in range(6):
                report['samples'].append(sample('shared_pl_idle'))
                time.sleep(2)
            report['shared_restore_started_s'] = time.monotonic()
            Overlay(original)
            shared_loaded = False
            report['shared_restore_completed_s'] = time.monotonic()
        for _ in range(8):
            report['samples'].append(sample('after'))
            time.sleep(2)
    except (Exception, KeyboardInterrupt) as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=25)
            except subprocess.TimeoutExpired:
                # Never SIGKILL a possibly active framebuffer owner.
                report['needs_attention'] = 'Eye cleanup did not finish; DMA ownership must be checked'
        if log is not None:log.close()
        if shared_loaded and not report.get('needs_attention'):
            try:
                Overlay(original)
            except Exception as error:
                report['restore_error'] = type(error).__name__ + ': ' + str(error)
                report['needs_attention'] = 'Original PL restoration failed; do not start another candidate'
        if pl_lock is not None:
            (CANDIDATE / 'shared_pl.json').unlink(missing_ok=True)
            pl_lock.close()
        report['current_pl'] = PL.bitfile_name
        report['pl_restored'] = report['current_pl'] == original
        report['services_after'] = services()
        report['services_unchanged'] = report['services_after'] == report['services_before']
        report['protected_after'] = protected_hashes()
        report['protected_files_unchanged'] = report['protected_after'] == report['protected_before']
        report['scope'] = 'Finite coexistence engineering test; not brain/eye accuracy validation'
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({key: report.get(key) for key in (
            'eye_exit_code', 'error', 'pl_restored', 'services_unchanged', 'protected_files_unchanged', 'needs_attention')}), flush=True)
    if report.get('eye_exit_code') != 0 or not report['pl_restored'] or report.get('needs_attention'):
        raise RuntimeError('Eye session or PL restoration did not pass')


if __name__ == '__main__':main()

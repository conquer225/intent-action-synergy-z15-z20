"""Authorized production application/PL reload; no boot, DT, or model changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.request import urlopen

APP = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
UNITS = ('guardianloop-cyton.service', 'guardianloop-web.service')
STARTUP = 'guardianloop-startup.service'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def api(name):
    with urlopen('http://127.0.0.1:9102/api/'+name, timeout=3) as response:
        return json.load(response)


def units():
    return subprocess.check_output(['systemctl', 'show', *UNITS, STARTUP,
        '-p', 'Id', '-p', 'ActiveState', '-p', 'SubState', '-p', 'MainPID', '-p', 'NRestarts'], text=True)


def audit(expected):
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if boot != expected['boot_id']:
        raise ValueError('Serial/SSH boot identity mismatch; no application writes')
    if (Path('/dev/guardianloop_dma_keeper').exists()
            or 'gldma' in Path('/proc/modules').read_text()):
        raise ValueError('Candidate DMA owner present; no PL reload')
    overlays = Path('/sys/kernel/config/device-tree/overlays')
    if overlays.exists() and any(overlays.iterdir()):
        raise ValueError('Device-tree overlay remains; inspect before PL reload')
    manifest = json.loads((APP/'release_manifest.json').read_text())
    if manifest != expected['manifest']:
        raise ValueError('Unexpected board release; do not overwrite another program')
    for path, checksum in expected['guard'].items():
        if sha(Path(path)) != checksum:
            raise ValueError('Foreign modification: '+path)
    views = {name:api(name) for name in ('mi-cue', 'ssvep-cue', 'ssvep-free', 'recording')}
    if any(views[name].get('state') not in ('idle', 'stopped')
           for name in ('mi-cue', 'ssvep-cue', 'ssvep-free')):
        raise ValueError('An experiment is active or unavailable; no reload')
    if views['recording'].get('recording', {}).get('state') in ('recording', 'starting', 'stopping'):
        raise ValueError('Raw recording active; no reload')
    if views['ssvep-free'].get('study', {}).get('state') not in ('not_created', 'complete'):
        raise ValueError('Unfinished study plan; no reload')
    for name in ('ssvep-cue', 'ssvep-free'):
        if views[name].get('recording_control', {}).get('owned_trial_id'):
            raise ValueError('Owned raw capture is pending; no reload')
    return dict(boot_id=boot, release=manifest['release_id'], files=len(manifest['files']),
                services=units(), views=views, candidate_dma_absent=True)


def service(action, *names):
    subprocess.run(['systemctl', action, *names], check=True, timeout=75)


def save(path, result):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def reload(stage, expected):
    if os.geteuid() != 0:
        raise PermissionError('Authorized reload requires sudo')
    report = dict(passed=False, stage='preflight', started_monotonic=time.monotonic(),
                  boot_files_changed=False, board_rebooted=False, physical_control=False)
    result_path = stage/'result.json'
    save(result_path, report)
    stopped = False
    changed = False
    try:
        report['before'] = audit(expected)
        names = [*expected['manifest']['files'], 'release_manifest.json']
        for name in names:
            if Path(name).name != name:
                raise ValueError('Application path escaped')
            source = stage/'runtime'/name
            checksum = expected['guard'][str(APP/name)]
            if sha(source) != checksum:
                raise ValueError('Staged file hash mismatch: '+name)
        backup = stage/'previous'
        backup.mkdir(mode=0o700)
        for name in names:
            target = APP/name
            if target.is_symlink():
                raise ValueError('Unexpected application symlink')
            shutil.copy2(target, backup/name)
        report['backup'] = str(backup)
        report['stage'] = 'stopping_services'
        save(result_path, report)
        stopped = True
        service('stop', *UNITS)
        report['stage'] = 'copying_identical_formal_release'
        save(result_path, report)
        changed = True
        for name in names:
            shutil.copy2(stage/'runtime'/name, APP/name)
        report['stage'] = 'formal_pl_and_model_selftest'
        save(result_path, report)
        service('restart', STARTUP)
        startup = json.loads(Path('/run/guardianloop-startup/status.json').read_text())
        if (startup.get('state') != 'ready' or startup.get('release_id') != expected['manifest']['release_id']
                or startup.get('boot_id') != expected['boot_id']
                or startup.get('pl', {}).get('ids') != {'de':'44453031', 'hgb':'48473031', 'model':'50537911'}):
            raise ValueError('Production PL/self-test identifiers did not match')
        report['startup'] = startup
        report['stage'] = 'starting_services'
        save(result_path, report)
        service('start', *UNITS)
        stopped = False
        deadline = time.monotonic()+45
        while True:
            try:
                after = audit(expected)
                break
            except (ValueError, OSError) as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Post-reload readiness failed') from exc
                time.sleep(1)
        pages = {}
        for path in ('/', '/mi-cued', '/ssvep-cued', '/ssvep-free'):
            with urlopen('http://127.0.0.1:9102'+path, timeout=3) as response:
                pages[path] = len(response.read())
        first = units()
        time.sleep(10)
        if units() != first:
            raise ValueError('Service PID or restart count changed during short check')
        report.update(passed=True, stage='complete', after=after, page_bytes=pages,
                      stable_services_seconds=10, completed_monotonic=time.monotonic(),
                      pl_reloaded=True, arm_application_recopied=True, models_changed=False,
                      service_and_boot_hashes_unchanged=True, human_accuracy_measured=False)
    except Exception as exc:
        report['error'] = type(exc).__name__+': '+str(exc)
        if changed:
            report['stage'] = 'restoring_original_application'
            save(result_path, report)
            try:
                service('stop', *UNITS)
                for path in (stage/'previous').iterdir():
                    shutil.copy2(path, APP/path.name)
                service('restart', STARTUP)
                report['application_rollback_completed'] = True
            except Exception as recovery:
                report['recovery_error'] = type(recovery).__name__+': '+str(recovery)
    finally:
        if stopped or not report['passed']:
            try:
                service('start', *UNITS)
            except Exception as recovery:
                report['service_recovery_error'] = type(recovery).__name__+': '+str(recovery)
        report['final_services'] = units()
        save(result_path, report)
    print(json.dumps(dict(passed=report['passed'], stage=report['stage'],
                         error=report.get('error'), result=str(result_path))), flush=True)
    return report['passed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('audit', 'reload'))
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    stage = args.stage.resolve()
    if stage.parent != Path('/home/xilinx') or not stage.name.startswith('formal-reload-'):
        raise ValueError('Stage outside the explicitly scoped board directory')
    expected = json.loads((stage/'expected.json').read_text())
    if args.action == 'audit':
        print(json.dumps(audit(expected)))
    elif not reload(stage, expected):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

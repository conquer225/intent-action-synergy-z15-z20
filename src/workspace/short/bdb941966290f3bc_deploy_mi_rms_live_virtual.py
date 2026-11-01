"""Verify then install a reboot-scoped base RMS virtual entry; preserve formal/study files."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

import numpy as np

from deploy_mi_live_virtual import FORMAL, protect, read_json
from run_mi_arm_acceptance import digest, dump, snapshot, stream_command
from run_soak_stage import connect, command
from run_ssvep_backlog_replay import checked

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'eeg_apps_z15/output/mi_rms_live_virtual_20261003'
PREVIOUS = ROOT / 'eeg_apps_z15/output/mi_personal_live_20261003/audit.json'
OVERRIDE = '/run/systemd/system/guardianloop-cyton.service.d/96-mi-rms-live-virtual.conf'
PRIOR_OVERRIDE = '/run/systemd/system/guardianloop-cyton.service.d/95-mi-personal-study.conf'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'
TESTS = 'test_mi_rms_live_virtual test_mi_cued test_mi_virtual test_mi_acquisition test_mi_reader_tap'
ADDITIONS = ('mi_rms_live_virtual.py', 'test_mi_rms_live_virtual.py',
             'mi_reader_tap_smoke.py', 'mi_saved_window_parity.py')


def live_state(client):
    probe = "import json;from urllib.request import urlopen;print(json.dumps(json.load(urlopen('http://127.0.0.1:9104/api/mi-cue',timeout=2))))"
    return json.loads(command(client, 'python3 -c ' + shlex.quote(probe)))


def study_hashes(client, remote):
    probe = ("import pathlib,hashlib,json;p=pathlib.Path(" + repr(remote) + ");"
             "paths=list(p.glob('study-*/*'))+list(p.glob('study-*/*/*'));"
             "print(json.dumps({str(x.relative_to(p)):hashlib.sha256(x.read_bytes()).hexdigest() "
             "for x in paths if x.is_file() and x.suffix in ('.json','.npz')}))")
    return json.loads(command(client, PYTHON + ' -c ' + shlex.quote(probe)))


def idle(client):
    with client.open_sftp() as sftp:
        if read_json(sftp, '/run/guardianloop/recording_status.json').get('state') == 'recording':
            raise RuntimeError('Active human recording; restart refused')
    state = live_state(client)
    if state['state'] in ('active', 'awaiting_presentation') or state.get('study', {}).get('phase') is not None:
        raise RuntimeError('Active human cue/block; restart refused')
    return state


def prepare(client):
    prior = json.loads(PREVIOUS.read_text(encoding='utf-8'))
    remote_old = prior['remote_directory']
    stage = OUT / 'stage'
    stage.mkdir()
    with client.open_sftp() as sftp:
        release = read_json(sftp, FORMAL + '/release_manifest.json')
        audit = dict(started_at=datetime.now().astimezone().isoformat(), deployed=False,
                     protected_before=protect(client, sftp, release), runtime_before=snapshot(client),
                     live_before=idle(client), prior_stage=remote_old,
                     prior_study_records_sha256=study_hashes(client, remote_old))
        expected = prior['override_sha256']
        if command(client, 'sha256sum ' + PRIOR_OVERRIDE).split()[0] != expected:
            raise RuntimeError('Previous runtime override changed; inspect first')
        audit['prior_override_sha256'] = expected
        checked(client, 'test ! -e ' + OVERRIDE)
        for name, expected in prior['stage_sha256'].items():
            if Path(name).suffix not in ('.py', '.html', '.json', '.npz', '.npy', '.bit', '.hwh'):
                continue
            path = stage / name
            sftp.get(remote_old + '/' + name, str(path))
            if digest(path) != expected:
                raise ValueError('Prior private source changed: ' + name)
    for name in ADDITIONS:
        shutil.copy2(ROOT / 'pynq_guardianloop' / name, stage / name)
    shutil.copy2(OUT / 'saved_window_probes.npz', stage / 'saved_window_probes.npz')
    remote = command(client, 'mktemp -d /home/xilinx/mi-rms-virtual-live-XXXXXX').strip()
    if not re.fullmatch(r'/home/xilinx/mi-rms-virtual-live-[A-Za-z0-9]+', remote):
        raise ValueError('Unexpected private path')
    audit['remote_directory'] = remote
    dump(OUT / 'deployment.json', audit)
    print('PRIVATE_STAGE_PREPARED', remote, flush=True)


def restore(client, audit):
    checked(client, 'test "$(sha256sum ' + OVERRIDE + " | cut -d' ' -f1)" + '" = ' + audit['override_sha256'], sudo=True)
    checked(client, 'test "$(sha256sum ' + PRIOR_OVERRIDE + " | cut -d' ' -f1)" + '" = ' + audit['prior_override_sha256'], sudo=True)
    checked(client, 'systemctl stop guardianloop-cyton.service', sudo=True)
    checked(client, 'rm -- ' + OVERRIDE, sudo=True)
    checked(client, 'systemctl daemon-reload', sudo=True)
    checked(client, 'systemctl start guardianloop-cyton.service', sudo=True)
    return checked(client, 'systemctl is-active guardianloop-cyton.service')


def deploy(client, audit):
    stage, remote = OUT / 'stage', audit['remote_directory']
    for name in ADDITIONS:
        if digest(stage / name) != digest(ROOT / 'pynq_guardianloop' / name):
            raise ValueError('New source differs from staged source: ' + name)
    prefix = 'cd ' + shlex.quote(remote) + ' && env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 '
    audit['stage_sha256'] = {p.name: digest(p) for p in stage.iterdir() if p.is_file()}
    with (OUT / 'pc_tests.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', *TESTS.split()],
                       cwd=stage, stdout=log, stderr=subprocess.STDOUT, check=True)
    parity_args = ['mi_saved_window_parity.py', '--input', 'saved_window_probes.npz',
                   '--model', 'experimental_rms_eegnet.npz']
    with (OUT / 'pc_parity.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, '-X', 'utf8', *parity_args, '--output', str(OUT / 'pc_parity.npz')],
                       cwd=stage, stdout=log, stderr=subprocess.STDOUT, check=True)
    with client.open_sftp() as sftp:
        for path in stage.iterdir():
            if path.is_file():
                sftp.put(str(path), remote + '/' + path.name)
                if command(client, 'sha256sum ' + shlex.quote(remote + '/' + path.name)).split()[0] != digest(path):
                    raise ValueError('Transfer mismatch: ' + path.name)
    stream_command(client, prefix + 'timeout 120s ' + PYTHON + ' -m unittest ' + TESTS, OUT / 'arm_tests.log', 125)
    stream_command(client, prefix + 'timeout 60s ' + PYTHON + ' ' + ' '.join(parity_args) + ' --output arm_parity.npz',
                   OUT / 'arm_parity.log', 65)
    stream_command(client, prefix + 'timeout 60s ' + PYTHON + ' mi_reader_tap_smoke.py --shared-rms --model experimental_rms_eegnet.npz --output tap_smoke.json',
                   OUT / 'arm_tap_smoke.log', 65)
    with client.open_sftp() as sftp:
        sftp.get(remote + '/arm_parity.npz', str(OUT / 'arm_parity.npz'))
        sftp.get(remote + '/tap_smoke.json', str(OUT / 'tap_smoke.json'))
        release = read_json(sftp, FORMAL + '/release_manifest.json')
        if protect(client, sftp, release) != audit['protected_before']:
            raise RuntimeError('Protected files changed during tests')
    with np.load(OUT / 'pc_parity.npz') as a, np.load(OUT / 'arm_parity.npz') as b:
        np.testing.assert_allclose(a['logits'], b['logits'], rtol=0, atol=1e-5)
        np.testing.assert_array_equal(a['logits'].argmax(1), b['logits'].argmax(1))
        audit['pc_arm_logit_max_error'] = float(np.max(np.abs(a['logits']-b['logits'])))
    idle(client)
    checked(client, 'test ! -e ' + OVERRIDE)
    checked(client, 'test "$(sha256sum ' + PRIOR_OVERRIDE + " | cut -d' ' -f1)" + '" = ' + audit['prior_override_sha256'], sudo=True)
    audit['override_sha256'] = digest(stage / 'virtual.conf')
    dump(OUT / 'deployment.json', audit)
    changed = False
    try:
        print('TEMPORARY_RESTART_CYTON_ONLY', flush=True)
        checked(client, 'systemctl stop guardianloop-cyton.service', sudo=True)
        checked(client, 'install -m 644 ' + shlex.quote(remote + '/virtual.conf') + ' ' + OVERRIDE, sudo=True)
        changed = True
        checked(client, 'systemctl daemon-reload', sudo=True)
        checked(client, 'systemctl start guardianloop-cyton.service', sudo=True)
        deadline = time.monotonic() + 45
        state = None
        while time.monotonic() < deadline:
            try:
                state = live_state(client)
            except RuntimeError:
                time.sleep(.5)
                continue
            if state.get('candidate_model', {}).get('personal_head_enabled') is False:
                break
            time.sleep(.5)
        if (state is None or 'candidate_model' not in state or state['source'] != 'live'
                or state['state'] != 'idle' or state['control_enabled'] is not False
                or state['virtual_hand']['enabled'] or state['virtual_hand']['command_count'] != 0
                or state['candidate_model']['personal_head_enabled'] is not False
                or state['channels'] != ['F3','F4','C3','C4','T7','T8','O1','O2']):
            raise RuntimeError('New base-only idle entry is not healthy')
        after = snapshot(client)
        with client.open_sftp() as sftp:
            protected_after = protect(client, sftp, release)
        if (after['hashes'] != audit['runtime_before']['hashes'] or protected_after != audit['protected_before']
                or after['services']['guardianloop-web.service'] != audit['runtime_before']['services']['guardianloop-web.service']
                or study_hashes(client, audit['prior_stage']) != audit['prior_study_records_sha256']):
            raise RuntimeError('Formal, boot, web or previous study artifacts changed')
        audit.update(deployed=True, protected_after=protected_after, runtime_after=after, live_snapshot=state,
                     url='http://192.168.2.99:9104/mi-cued', formal_files_unchanged=True,
                     study_records_unchanged=True, permanent_startup_changed=False, pl_changed=False,
                     physical_control=False, personal_head_enabled=False, model_promoted=False,
                     new_wearer_accuracy_scored=False,
                     rollback='python eeg_apps_z15/deploy_mi_rms_live_virtual.py --restore')
        print('BASE_RMS_VIRTUAL_LIVE_READY', json.dumps(state, ensure_ascii=False), flush=True)
    except BaseException:
        if changed:
            audit['rollback_result'] = restore(client, audit)
        else:
            checked(client, 'systemctl start guardianloop-cyton.service', sudo=True)
        raise
    finally:
        dump(OUT / 'deployment.json', audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--deploy', action='store_true')
    action.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    client = connect()
    try:
        if args.prepare:
            prepare(client)
        else:
            audit = json.loads((OUT / 'deployment.json').read_text(encoding='utf-8'))
            if args.deploy:
                deploy(client, audit)
            else:
                audit.update(deployed=False, rollback_result=restore(client, audit))
                dump(OUT / 'deployment.json', audit)
    finally:
        client.close()


if __name__ == '__main__':
    main()

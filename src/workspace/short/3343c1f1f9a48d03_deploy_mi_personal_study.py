"""Stage/tests live RMS study; runtime-only override, exact guarded rollback."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

import numpy as np

from run_soak_stage import connect, command
from run_ssvep_backlog_replay import checked
from run_mi_arm_acceptance import snapshot, dump, digest, stream_command
from deploy_mi_live_virtual import protect, read_json, FORMAL

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'eeg_apps_z15/output/mi_personal_live_20261003'
OLD = '/home/xilinx/mi-live-virtual-20261003-a1'
OVERRIDE = '/run/systemd/system/guardianloop-cyton.service.d/95-mi-personal-study.conf'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'
FILES = ('mi_eegnet_rms.py', 'mi_window_rms.py', 'mi_personal_study.py', 'mi_personal_server.py',
         'mi_personal_study.html', 'test_mi_personal_study.py', 'mi_personal_parity.py',
         'test_mi_cued.py', 'test_mi_virtual.py', 'test_mi_acquisition.py', 'test_mi_reader_tap.py')
TESTS = 'test_mi_personal_study test_mi_cued test_mi_virtual test_mi_acquisition test_mi_reader_tap'


def rollback(client, audit):
    remote = audit['remote_directory']
    expected = audit['override_sha256']
    # Only the one runtime override created by this experiment may be removed.
    checked(client, 'test "$(sha256sum '+shlex.quote(OVERRIDE)+" | cut -d' ' -f1)"+'" = '+expected, sudo=True)
    checked(client, 'systemctl stop guardianloop-cyton.service', sudo=True)
    checked(client, 'rm -- '+shlex.quote(OVERRIDE), sudo=True)
    checked(client, 'systemctl daemon-reload', sudo=True)
    checked(client, 'systemctl start guardianloop-cyton.service', sudo=True)
    return checked(client, 'systemctl is-active guardianloop-cyton.service')


def prepare(client, out, audit):
    stage = out/'stage'
    stage.mkdir()
    with client.open_sftp() as sftp:
        release = read_json(sftp, FORMAL+'/release_manifest.json')
        audit['protected_before'] = protect(client, sftp, release)
        audit['runtime_before'] = snapshot(client)
        audit['old_stage_hashes'] = {}
        for item in sftp.listdir_attr(OLD):
            name = item.filename
            if Path(name).suffix not in ('.py', '.html', '.json', '.npz', '.npy', '.bit', '.hwh'):
                continue
            path = OLD+'/'+name
            with sftp.open(path, 'rb') as stream:
                data = stream.read()
            audit['old_stage_hashes'][name] = hashlib.sha256(data).hexdigest()
            with (stage/name).open('wb') as stream:
                stream.write(data)
        checked(client, 'test ! -e '+OVERRIDE)
    for name in FILES:
        shutil.copy2(ROOT/'pynq_guardianloop'/name, stage/name)
    shutil.copy2(ROOT/'eeg_apps_z15/output/mi_rms_runtime_20261003/mi_eegnet_portable.py',
                 stage/'mi_eegnet_frozen_rms.py')
    shutil.copy2(ROOT/'eeg_apps_z15/output/mi_rms_comparison_20261003/experimental_rms_eegnet.npz',
                 stage/'experimental_rms_eegnet.npz')
    shutil.copy2(ROOT/'eeg_apps_z15/MI_RMS_LIVE_PLAN.md', stage/'MI_RMS_LIVE_PLAN.md')
    remote = command(client, 'mktemp -d /home/xilinx/mi-rms-live-XXXXXX').strip()
    if re.fullmatch(r'/home/xilinx/mi-rms-live-[A-Za-z0-9]+', remote) is None:
        raise ValueError('Unexpected private path')
    audit['remote_directory'] = remote
    dump(out/'audit.json', audit)
    print('Prepared private copy. Apply the explicit worker/config patch, then run --deploy.', flush=True)


def deploy(client, out, audit):
    stage, remote = out/'stage', audit['remote_directory']
    override = '[Service]\nWorkingDirectory='+remote+'\nEnvironment=PYTHONDONTWRITEBYTECODE=1\n'+\
        'Environment=OPENBLAS_NUM_THREADS=1\nEnvironment=OMP_NUM_THREADS=1\nExecStart=\nExecStart='+PYTHON+' '+remote+\
        '/mi_live_acquisition.py --windows 0 --filter-backend arm --channel-map F3,F4,C3,C4,T7,T8,O1,O2 '+\
        '--esp32-url= --status-file /run/guardianloop/status.json --telemetry-file /run/guardianloop/telemetry.json\n'
    # Generated per-directory configuration, not an edit of /etc or startup images.
    (stage/'personal.conf').write_text(override, encoding='utf-8')
    audit['override_sha256'] = digest(stage/'personal.conf')
    audit['stage_sha256'] = {p.name: digest(p) for p in stage.iterdir() if p.is_file()}
    dump(out/'audit.json', audit)
    with (out/'pc_tests.log').open('w', encoding='utf-8') as log:
        result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', *TESTS.split()],
                                cwd=stage, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('PC regression failed')
    result = subprocess.run([sys.executable, '-X', 'utf8', 'mi_personal_parity.py', '--output',str(out/'pc_parity.npz')],
                            cwd=stage, check=True, capture_output=True)
    (out/'pc_parity.log').write_bytes(result.stdout+result.stderr)
    with client.open_sftp() as sftp:
        for path in stage.iterdir():
            if not path.is_file(): continue
            sftp.put(str(path), remote+'/'+path.name)
            if command(client, 'sha256sum '+shlex.quote(remote+'/'+path.name)).split()[0] != digest(path):
                raise ValueError('Transfer mismatch: '+path.name)
    prefix = 'cd '+shlex.quote(remote)+' && env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 '
    stream_command(client, prefix+'timeout 120s '+PYTHON+' -m unittest '+TESTS, out/'arm_tests.log', 125)
    stream_command(client, prefix+'timeout 40s '+PYTHON+' mi_personal_parity.py --output arm_parity.npz',out/'arm_parity.log',45)
    with client.open_sftp() as sftp:
        sftp.get(remote+'/arm_parity.npz',str(out/'arm_parity.npz'))
        release = read_json(sftp, FORMAL+'/release_manifest.json')
        if protect(client,sftp,release) != audit['protected_before']:
            raise RuntimeError('Protected files changed during preparation')
        if read_json(sftp,'/run/guardianloop/recording_status.json').get('state') == 'recording':
            raise RuntimeError('Human recording active; no restart')
    with np.load(out/'pc_parity.npz') as a, np.load(out/'arm_parity.npz') as b:
        errors = {}
        for key in a.files:
            np.testing.assert_allclose(a[key], b[key], rtol=1e-7, atol=1e-5)
            errors[key] = float(np.max(np.abs(a[key]-b[key])))
        np.testing.assert_array_equal(a['logits'].argmax(1),b['logits'].argmax(1))
        np.testing.assert_array_equal(a['personal_logits'].argmax(1),b['personal_logits'].argmax(1))
    audit['pc_arm_max_absolute_errors'] = errors
    checked(client,'test ! -e '+OVERRIDE)
    changed = False
    try:
        checked(client,'systemctl stop guardianloop-cyton.service',sudo=True)
        checked(client,'install -m 644 '+shlex.quote(remote+'/personal.conf')+' '+OVERRIDE,sudo=True)
        changed = True
        checked(client,'systemctl daemon-reload',sudo=True)
        checked(client,'systemctl start guardianloop-cyton.service',sudo=True)
        probe = "import json;from urllib.request import urlopen;print(json.dumps(json.load(urlopen('http://127.0.0.1:9104/api/mi-cue',timeout=2))))"
        deadline = time.monotonic()+45
        state = None
        while time.monotonic()<deadline:
            try:
                state = json.loads(command(client,'python3 -c '+shlex.quote(probe)))
                if state.get('study') and state.get('received_samples',0)>=500: break
            except RuntimeError:
                pass
            time.sleep(.5)
        if (state is None or not state.get('study') or state['source']!='live'
                or state['input_state']!='ready' or state['control_enabled'] is not False):
            raise RuntimeError('New live entry not ready')
        with client.open_sftp() as sftp:
            audit['protected_after'] = protect(client,sftp,release)
        if audit['protected_after'] != audit['protected_before']:
            raise RuntimeError('Protected formal artifacts changed')
        audit['runtime_after'] = snapshot(client)
        if audit['runtime_after']['services']['guardianloop-web.service'] != audit['runtime_before']['services']['guardianloop-web.service']:
            raise RuntimeError('Web service changed unexpectedly')
        audit.update(deployed=True, formal_unchanged=True, boot_and_pl_unchanged=True,
                     live_snapshot=state,url='http://192.168.2.99:9104/mi-cued',
                     control_enabled=False, model_promoted=False, wearer_accuracy_scored=False)
        print('LIVE_STUDY_READY', json.dumps(state,ensure_ascii=False),flush=True)
    except BaseException:
        if changed:
            audit['rollback'] = rollback(client,audit)
        else:
            checked(client,'systemctl start guardianloop-cyton.service',sudo=True)
        raise
    finally:
        dump(out/'audit.json',audit)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--deploy',action='store_true')
    parser.add_argument('--restore',action='store_true')
    args=parser.parse_args()
    if sum((args.prepare,args.deploy,args.restore))!=1: parser.error('Choose one action')
    client=connect()
    try:
        if args.prepare:
            OUT.mkdir(exist_ok=False)
            audit=dict(started_at=datetime.now().astimezone().isoformat(),deployed=False)
            prepare(client,OUT,audit)
        else:
            audit=json.loads((OUT/'audit.json').read_text(encoding='utf-8'))
            if args.restore:
                audit['rollback']=rollback(client,audit)
                audit['deployed']=False
                dump(OUT/'audit.json',audit)
            else:
                deploy(client,OUT,audit)
    finally:
        client.close()


if __name__=='__main__':
    main()

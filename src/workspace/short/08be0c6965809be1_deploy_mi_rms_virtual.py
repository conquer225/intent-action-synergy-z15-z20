"""Create and verify a private recorded-only shared-RMS virtual page on Z15."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

import numpy as np

from run_soak_stage import connect, command
from run_mi_arm_acceptance import digest, dump, snapshot, stream_command


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT/'eeg_apps_z15'
RUNTIME = ROOT/'pynq_guardianloop'
PREVIOUS = APP/'output/mi_rms_arm_acceptance_20261003'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'
NEW_FILES = ('mi_rms_virtual_replay.py','mi_rms_virtual_page.html','mi_rms_virtual_ui.js',
             'mi_rms_virtual_checks.py','test_mi_rms_virtual.py')
OLD_FILES = ('mi_cued.py','mi_cued.html','mi_features.py','cyton_sqi.py','mi_cued_server.py',
             'mi_cued_replay.py','mi_cued_acceptance.py','mi_eegnet_portable.py','mi_eegnet_rms.py',
             'mi_window_rms.py','experimental_rms_eegnet.npz','bench_input.npz',
             'test_mi_cued.py','test_mi_rms_arm.py','test_mi_eegnet_portable.py')
TESTS = ('test_mi_cued','test_mi_virtual','test_mi_eegnet_portable','test_mi_rms_arm','test_mi_rms_virtual')


def protected(client):
    state = snapshot(client)
    state['boot_id'] = command(client,'cat /proc/sys/kernel/random/boot_id').strip()
    state['mi_config_sha256'] = command(client,'sha256sum /etc/default/guardianloop-mi.json').split()[0]
    return state


def compare_replays(pc, arm):
    checks = {}
    for name in ('observe','virtual'):
        with np.load(pc/name/'arrays.npz') as a, np.load(arm/name/'arrays.npz') as b:
            np.testing.assert_allclose(a['logits'],b['logits'],rtol=0,atol=1e-4)
            np.testing.assert_array_equal(a['logits'].argmax(1),b['logits'].argmax(1))
            np.testing.assert_array_equal(a['valid'],b['valid'])
            for key in ('conditioned','filtered'):
                np.testing.assert_allclose(a[key],b[key],rtol=1e-7,atol=1e-6,equal_nan=True)
            checks[name+'_max_logit_error'] = float(np.max(np.abs(a['logits']-b['logits'])))
        left = json.loads((pc/name/'replay.json').read_text(encoding='utf-8'))
        right = json.loads((arm/name/'replay.json').read_text(encoding='utf-8'))
        if left['trace']!=right['trace']:
            raise ValueError('PC/ARM states differ: '+name)
        if len(left['results'])!=len(right['results']):
            raise ValueError('PC/ARM prediction count differs')
        for a,b in zip(left['results'],right['results']):
            if {k:v for k,v in a.items() if k!='logits'}!={k:v for k,v in b.items() if k!='logits'}:
                raise ValueError('PC/ARM windows or classes differ')
    def commands(folder):
        events = [json.loads(line) for line in (folder/'virtual/events.jsonl').read_text().splitlines()]
        fields = ('label','action','position_before','position_after','sequence','source','simulation','control_enabled')
        return [{key:event[key] for key in fields} for event in events if event['event']=='virtual_command']
    if commands(pc)!=commands(arm):
        raise ValueError('PC/ARM virtual command sequence differs')
    return dict(checks, classes_windows_states_and_commands_exact=True, passed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=APP/'output/mi_rms_virtual_20261003')
    args = parser.parse_args()
    out = args.output.resolve()
    prior = json.loads((PREVIOUS/'audit.json').read_text(encoding='utf-8'))
    if not prior['passed']:
        raise ValueError('Previous RMS ARM acceptance did not pass')
    previous_manifest = json.loads((PREVIOUS/'OUTPUT_SHA256.json').read_text(encoding='utf-8'))
    # The old stage is evidence. Copy it; never edit it or the frozen model.
    out.mkdir(exist_ok=False)
    stage = out/'stage'
    stage.mkdir()
    for name in OLD_FILES:
        source = PREVIOUS/'stage'/name
        expected = previous_manifest.get('stage/'+name)
        if expected is None:
            expected = previous_manifest.get(str(source))
        if expected is None or digest(source)!=expected:
            raise ValueError('Previous stage checksum failed: '+name)
        shutil.copy2(source,stage/name)
    for name in NEW_FILES+('test_mi_virtual.py',):
        shutil.copy2(RUNTIME/name,stage/name)
    shutil.copy2(APP/'MI_RMS_VIRTUAL_PLAN.md',stage/'MI_RMS_VIRTUAL_PLAN.md')
    hashes = {str(path):digest(path) for path in stage.iterdir() if path.is_file()}
    audit = dict(started_at=datetime.now().astimezone().isoformat(),source_sha256=hashes,
                 accuracy_scored=False,model_retrained=False,pl_changed=False,
                 control_enabled=False,production_eligible=False,passed=False)
    dump(out/'audit.json',audit)
    env = dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    def pc_run(arguments,log):
        with (out/log).open('w',encoding='utf-8') as stream:
            result = subprocess.run([sys.executable,'-X','utf8',*arguments],cwd=stage,env=env,
                                    stdout=stream,stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError('PC checks failed: '+log)
    pc_run(['-m','unittest',*TESTS],'pc_tests.log')
    pc_run(['mi_rms_virtual_checks.py','--output',str(out/'pc')],'pc_functional.log')
    client = connect()
    launched = None
    try:
        client.get_transport().set_keepalive(15)
        audit['before'] = protected(client)
        recording = json.loads(command(client,'cat /run/guardianloop/recording_status.json'))
        if recording.get('active') or recording.get('state')=='recording':
            raise RuntimeError('Active human recording: isolated run deferred')
        if any(v['ActiveState']!='active' for v in audit['before']['services'].values()):
            raise RuntimeError('Formal service not active')
        remote = command(client,'mktemp -d /home/xilinx/mi-rms-virtual-XXXXXX').strip()
        if re.fullmatch(r'/home/xilinx/mi-rms-virtual-[A-Za-z0-9]+',remote) is None:
            raise ValueError('Unexpected private directory')
        audit['remote_directory'] = remote
        with client.open_sftp() as sftp:
            for path in stage.iterdir():
                target = remote+'/'+path.name
                sftp.put(str(path),target)
                if command(client,'sha256sum '+shlex.quote(target)).split()[0]!=digest(path):
                    raise ValueError('Transfer mismatch: '+path.name)
        dump(out/'audit.json',audit)
        prefix = 'cd '+shlex.quote(remote)+' && timeout --signal=TERM --kill-after=5s '
        runtime = 'nice -n 10 env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 '+PYTHON+' '
        stream_command(client,prefix+'90s '+runtime+'-m unittest '+' '.join(TESTS),out/'arm_tests.log',100)
        stream_command(client,prefix+'180s '+runtime+'mi_rms_virtual_checks.py --output arm',out/'arm_functional.log',190)
        arm = out/'arm'
        arm.mkdir()
        with client.open_sftp() as sftp:
            for child in ('report.json','observe/replay.json','observe/events.jsonl','observe/arrays.npz',
                          'virtual/replay.json','virtual/events.jsonl','virtual/arrays.npz'):
                target = arm/child
                target.parent.mkdir(exist_ok=True)
                sftp.get(remote+'/arm/'+child,str(target))
        audit['functional_report'] = json.loads((arm/'report.json').read_text(encoding='utf-8'))
        if not audit['functional_report']['passed']:
            raise ValueError('ARM virtual gates failed')
        audit['pc_arm_parity'] = compare_replays(out/'pc',arm)
        launch = """import subprocess,pathlib,json
root=pathlib.Path(%s)
with (root/'server.log').open('wb') as log:
 process=subprocess.Popen(['nice','-n','10','env','PYTHONDONTWRITEBYTECODE=1','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',%s,'mi_rms_virtual_replay.py','--model','experimental_rms_eegnet.npz','--input','bench_input.npz','--allow-experimental','--host','0.0.0.0','--port','0','--ready-file','ready.json','--audit-log','http_events.jsonl'],cwd=str(root),stdout=log,stderr=log,start_new_session=True)
print(json.dumps({'pid':process.pid}))
""" % (repr(remote),repr(PYTHON))
        launched = json.loads(command(client,PYTHON+' -c '+shlex.quote(launch)))['pid']
        audit['process_pid'] = launched
        with client.open_sftp() as sftp:
            ready = None
            deadline = time.monotonic()+35
            while time.monotonic()<deadline:
                try:
                    with sftp.open(remote+'/ready.json') as stream:
                        ready = json.load(stream)
                except FileNotFoundError:
                    time.sleep(.25)
                    continue
                break
        if ready is None or ready['pid']!=launched:
            log = command(client,'tail -30 '+shlex.quote(remote+'/server.log'))
            raise RuntimeError('Private HTTP process did not become ready: '+log)
        audit['ready'] = ready
        audit['url'] = 'http://192.168.2.99:'+str(ready['port'])+'/mi-cued'
        dump(out/'audit.json',audit)
        base = 'http://127.0.0.1:'+str(ready['port'])
        stream_command(client,prefix+'45s '+runtime+'mi_rms_virtual_checks.py --base-url '+base+' --output http',out/'arm_http.log',55)
        with client.open_sftp() as sftp:
            sftp.get(remote+'/http/report.json',str(out/'http_report.json'))
            sftp.get(remote+'/http_events.jsonl',str(out/'http_events.jsonl'))
            sftp.get(remote+'/ready.json',str(out/'ready.json'))
            sftp.get(remote+'/server.log',str(out/'server.log'))
        audit['http_report'] = json.loads((out/'http_report.json').read_text(encoding='utf-8'))
        audit['passed'] = audit['http_report']['passed']
    except Exception as error:
        audit['failure'] = dict(type=type(error).__name__,message=str(error))
        raise
    finally:
        try:
            audit['after'] = protected(client)
            audit['production_unchanged'] = audit.get('before')==audit['after']
            audit['source_files_unchanged'] = all(digest(path)==expected for path,expected in hashes.items())
            audit['passed'] = audit['passed'] and audit['production_unchanged'] and audit['source_files_unchanged']
            if launched and not audit['passed']:
                check = "import pathlib,os,signal; p=%d; cmd=pathlib.Path('/proc/'+str(p)+'/cmdline').read_bytes(); assert b'mi_rms_virtual_replay.py' in cmd; os.kill(p,signal.SIGTERM)" % launched
                command(client,PYTHON+' -c '+shlex.quote(check))
                audit['failed_candidate_stopped'] = True
        finally:
            audit['finished_at'] = datetime.now().astimezone().isoformat()
            dump(out/'audit.json',audit)
            client.close()
    if not audit['passed']:
        raise RuntimeError('Final isolation checks failed')
    print('RMS_VIRTUAL_ACCEPTED',audit['url'],'PID',launched,flush=True)


if __name__=='__main__':
    main()

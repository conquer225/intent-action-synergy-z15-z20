"""Stage and run bounded MI tests in a private Z15 directory, preserving production."""
import argparse
from datetime import datetime
import hashlib
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

from run_soak_stage import connect, command, PROD

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT/'pynq_guardianloop'
FROZEN = ROOT/'eeg_apps_z15/output/mi_cued_delivery_20261002_final'
BENCH = ROOT/'eeg_apps_z15/output/accepted_bench_load_20260927/bench_input.npz'
WAVES = ROOT/'eeg_apps_z15/output/mi_model_comparison_20261001/waveforms.npy'
ASSETS = ('mi_cued_acceptance.py','mi_cued.py','mi_cued_replay.py','mi_eegnet_portable.py',
          'mi_cued_server.py','mi_cued.html','cyton_sqi.py','mi_features.py',
          'test_mi_cued.py','test_mi_cued_replay.py','test_mi_eegnet_portable.py',
          'test_mi_cued_acceptance.py')
PYTHON = '/usr/local/share/pynq-venv/bin/python3'


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def snapshot(client):
    probe = """import pathlib,hashlib,json
root=pathlib.Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
paths=[p for p in root.iterdir() if p.is_file() and p.suffix in ('.py','.json','.npz','.bit','.hwh','.sh','.service')]
paths += [pathlib.Path(p) for p in ('/boot/BOOT.BIN','/boot/boot.py','/boot/boot.scr','/boot/image.ub','/boot/guardianloop_coexist_20260929.dtb','/etc/systemd/system/guardianloop-cyton.service','/etc/systemd/system/guardianloop-web.service','/etc/systemd/system/guardianloop-cyton-pl.service') if pathlib.Path(p).is_file()]
print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}))
"""
    hashes = json.loads(command(client,PYTHON+' -c '+shlex.quote(probe)))
    services = {}
    for unit in ('guardianloop-cyton.service','guardianloop-web.service'):
        text = command(client,'systemctl show '+unit+' --property=Id,MainPID,ActiveState,SubState,NRestarts')
        services[unit] = dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    return dict(hashes=hashes,services=services)


def stream_command(client, invoke, path, limit):
    channel = client.get_transport().open_session()
    channel.set_combine_stderr(True)
    channel.exec_command(invoke)
    deadline = time.monotonic()+limit
    with path.open('wb') as log:
        try:
            while True:
                if channel.recv_ready():
                    data = channel.recv(65536)
                    log.write(data)
                    log.flush()
                    print(data.decode('utf-8',errors='replace').rstrip(),flush=True)
                elif channel.exit_status_ready():
                    break
                elif time.monotonic()>deadline:
                    raise TimeoutError('Bounded remote test exceeded '+str(limit)+' seconds')
                else:
                    time.sleep(.1)
            code = channel.recv_exit_status()
            if code:
                raise RuntimeError('Remote command failed with '+str(code)+'; see '+str(path))
        finally:
            channel.close()


def compare(pc, arm):
    errors = {}
    for filename, fields in (('probes.npz',('logits',)),('arrays.npz',('conditioned','filtered','logits'))):
        with np.load(pc/filename,allow_pickle=False) as a, np.load(arm/filename,allow_pickle=False) as b:
            if filename=='arrays.npz':
                np.testing.assert_array_equal(a['valid'],b['valid'])
                np.testing.assert_array_equal(np.flatnonzero(~a['valid']),np.arange(50))
            for name in fields:
                left,right = a[name],b[name]
                if filename=='arrays.npz' and name!='logits':
                    if not np.isnan(left[~a['valid']]).all() or not np.isnan(right[~b['valid']]).all():
                        raise ValueError('Invalid samples have fabricated values')
                    left,right = left[a['valid']],right[b['valid']]
                if not np.isfinite(left).all() or not np.isfinite(right).all():
                    raise ValueError('Nonfinite parity output: '+name)
                atol, rtol = (1e-4,0) if name=='logits' else (1e-6,1e-7)
                np.testing.assert_allclose(left,right,atol=atol,rtol=rtol)
                errors[filename+':'+name] = float(np.max(np.abs(left-right)))
                if name=='logits':
                    np.testing.assert_array_equal(a[name].argmax(1),b[name].argmax(1))
            if filename=='probes.npz':
                np.testing.assert_array_equal(a['indices'],b['indices'])
    a = json.loads((pc/'replay.json').read_text(encoding='utf-8'))
    b = json.loads((arm/'replay.json').read_text(encoding='utf-8'))
    if a['trace']!=b['trace']:
        raise ValueError('Discrete stream state mismatch')
    for left,right in zip(a['results'],b['results']):
        if {k:v for k,v in left.items() if k!='logits'}!={k:v for k,v in right.items() if k!='logits'}:
            raise ValueError('Candidate discrete output mismatch')
    if len(a['results'])!=len(b['results']):
        raise ValueError('Candidate count mismatch')
    pa = json.loads((pc/'report.json').read_text(encoding='utf-8'))
    pb = json.loads((arm/'report.json').read_text(encoding='utf-8'))
    if pa['fault_checks']!=pb['fault_checks']:
        raise ValueError('Recovery state mismatch')
    return dict(passed=True,maximum_absolute_errors=errors,classes_exact=True,
                valid_samples=38950,initial50_invalid_mask_exact=True,
                full_stream_states_exact=True,windows_exact=True,recovery_exact=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'eeg_apps_z15/output/mi_arm_acceptance_20261002')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    frozen = json.loads((FROZEN/'lock.json').read_text(encoding='utf-8'))
    for path,expected in frozen['input_sha256'].items():
        if digest(path)!=expected:
            raise ValueError('Original input changed: '+path)
    accepted = json.loads((FROZEN/'acceptance.json').read_text(encoding='utf-8'))
    model = FROZEN/'experimental_eegnet.npz'
    if digest(model)!=accepted['experimental_artifact_sha256']:
        raise ValueError('Frozen model changed')
    with np.load(model,allow_pickle=False) as data:
        metadata = json.loads(str(data['metadata'].item()))
    if any(metadata[key] is not False for key in ('promotion_gate_passed','production_eligible','control_enabled')):
        raise ValueError('Not the locked experimental model')
    stage_files = [RUNTIME/name for name in ASSETS]+[model,BENCH]
    indices = np.linspace(0,6079,256,dtype=np.int64)
    waves = np.load(WAVES,mmap_mode='r',allow_pickle=False)
    probe = out/'probe_input.npz'
    np.savez_compressed(probe,indices=indices,waveforms=np.asarray(waves[indices]))
    stage_files.append(probe)
    source_paths = stage_files+[Path(__file__),ROOT/'eeg_apps_z15/MI_ARM_ACCEPTANCE_PLAN.md',
                               ROOT/'eeg_apps_z15/MI_ARM_ACCEPTANCE_AMENDMENT.md']
    hashes = {str(p):digest(p) for p in source_paths}
    copies = out/'code_snapshot'
    copies.mkdir()
    for path in source_paths:
        if path.suffix in ('.py','.html','.md'):
            shutil.copy2(path,copies/path.name)
    audit = dict(started_at_local=datetime.now().isoformat(),scope='isolated ARM functional verification',
                 source_sha256=hashes,original_input_sha256=frozen['input_sha256'],
                 score_atol=1e-4,filter_atol=1e-6,filter_rtol=1e-7,
                 training=False,accuracy_scored=False,promotion_gate_passed=False,
                 production_eligible=False,control_enabled=False,passed=False)
    dump(out/'audit.json',audit)
    client = connect()
    try:
        client.get_transport().set_keepalive(15)
        audit['before'] = snapshot(client)
        if audit['before']['services']['guardianloop-web.service']['ActiveState']!='active':
            raise RuntimeError('Existing web service is not healthy; stop before staging')
        audit['board_kernel'] = command(client,'uname -srmo').strip()
        audit['board_memory_before'] = command(client,'free -m')
        remote = command(client,'mktemp -d /home/xilinx/mi-arm-acceptance-XXXXXX').strip()
        if re.fullmatch(r'/home/xilinx/mi-arm-acceptance-[A-Za-z0-9]+',remote) is None:
            raise ValueError('Unexpected private directory')
        audit['remote_directory'] = remote
        with client.open_sftp() as sftp:
            for path in stage_files:
                target = remote+'/'+path.name
                sftp.put(str(path),target)
                if command(client,'sha256sum '+shlex.quote(target)).split()[0]!=hashes[str(path)]:
                    raise ValueError('Transfer mismatch: '+path.name)
        dump(out/'audit.json',audit)
        invocation = ['--model',str(model),'--input',str(BENCH),'--probes',str(probe),
                      '--output',str(out/'pc'),'--allow-experimental']
        with (out/'pc.log').open('w',encoding='utf-8') as log:
            process = subprocess.run([sys.executable,'-X','utf8',str(RUNTIME/'mi_cued_acceptance.py'),*invocation],
                stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,
                OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
        if process.returncode:
            raise RuntimeError('PC reference failed; see pc.log')
        prefix = ('cd '+shlex.quote(remote)+' && timeout --signal=TERM --kill-after=5s ')
        env = 'nice -n 10 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 '+PYTHON+' '
        stream_command(client,prefix+'60s '+env+'-m unittest test_mi_cued test_mi_cued_replay test_mi_eegnet_portable test_mi_cued_acceptance',
                       out/'arm_unit_tests.log',70)
        base = env+'mi_cued_acceptance.py --model experimental_eegnet.npz --input bench_input.npz '+\
            '--probes probe_input.npz --allow-experimental --output '
        for name,extra,limit in (('arm',' --http-recovery',120),('arm_paced',' --paced',300)):
            print('MI_ARM_STAGE',name,flush=True)
            stream_command(client,prefix+str(limit)+'s '+base+name+extra,out/(name+'.log'),limit+15)
            local = out/name
            local.mkdir()
            with client.open_sftp() as sftp:
                for filename in ('report.json','replay.json','probes.npz','arrays.npz','events.jsonl'):
                    sftp.get(remote+'/'+name+'/'+filename,str(local/filename))
                if name=='arm':
                    sftp.get(remote+'/'+name+'/http_child.log',str(local/'http_child.log'))
            audit[name+'_parity'] = compare(out/'pc',local)
            audit[name+'_report'] = json.loads((local/'report.json').read_text(encoding='utf-8'))
            if name=='arm_paced' and not audit[name+'_report']['summary']['paced_gate_passed']:
                raise ValueError('Declared paced-load gate failed')
            dump(out/'audit.json',audit)
        audit['passed'] = True
    except Exception as error:
        audit['failure'] = dict(type=type(error).__name__,message=str(error))
        raise
    finally:
        try:
            audit['after'] = snapshot(client)
            audit['production_files_unchanged'] = audit.get('before',{}).get('hashes')==audit['after']['hashes']
            audit['web_process_unchanged'] = audit.get('before',{}).get('services',{}).get('guardianloop-web.service')==audit['after']['services']['guardianloop-web.service']
            audit['source_files_unchanged'] = all(digest(path)==expected for path,expected in hashes.items())
            audit['original_inputs_unchanged'] = all(digest(path)==expected for path,expected in frozen['input_sha256'].items())
            if not all(audit[key] for key in ('production_files_unchanged','web_process_unchanged','source_files_unchanged','original_inputs_unchanged')):
                audit['passed'] = False
        finally:
            audit['finished_at_local'] = datetime.now().isoformat()
            dump(out/'audit.json',audit)
            client.close()
    if not audit['passed']:
        raise RuntimeError('Final preservation check failed')
    print('MI_ARM_ACCEPTED',audit['remote_directory'],flush=True)


if __name__=='__main__':
    main()

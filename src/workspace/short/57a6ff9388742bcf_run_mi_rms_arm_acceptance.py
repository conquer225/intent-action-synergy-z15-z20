"""Private recorded-only RMS checks, with before/after production safeguards."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import os
import sys

import numpy as np

from run_soak_stage import connect, command
from run_mi_arm_acceptance import digest, dump, snapshot, stream_command, compare

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT/'eeg_apps_z15'
RUNTIME = ROOT/'pynq_guardianloop'
RUN = APP/'output/mi_rms_comparison_20261003'
ISOLATED = APP/'output/mi_rms_runtime_20261003'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'
ASSETS = ('mi_cued.py','mi_features.py','cyton_sqi.py','mi_eegnet_portable.py',
          'mi_cued_acceptance.py','mi_cued_replay.py','mi_cued_server.py','mi_cued.html',
          'test_mi_cued.py','test_mi_eegnet_portable.py','test_mi_rms_arm.py',
          'mi_rms_arm_checks.py')


def compare_gain(pc, arm):
    with np.load(pc/'gain_probes.npz',allow_pickle=False) as a, np.load(arm/'gain_probes.npz',allow_pickle=False) as b:
        for field in ('factors','source_indices','trial_ids'):
            np.testing.assert_array_equal(a[field],b[field])
        np.testing.assert_allclose(a['logits'],b['logits'],rtol=0,atol=1e-4)
        np.testing.assert_array_equal(a['logits'].argmax(2),b['logits'].argmax(2))
        return dict(max_logit_error=float(np.max(np.abs(a['logits']-b['logits']))),classes_exact=True,
                    source_windows=16,real_windows=7,accuracy_scored=False)


def prepare(output):
    output.mkdir(exist_ok=False)
    result = json.loads((RUN/'results.json').read_text(encoding='utf-8'))
    audited = json.loads((RUN/'audit.json').read_text(encoding='utf-8'))
    if not result['continuation_gate_passed'] or audited['models_audited']!=90:
        raise ValueError('Frozen comparison did not pass isolation gate/audit')
    lock = json.loads((RUN/'lock.json').read_text(encoding='utf-8'))
    for name,expected in lock['source_sha256'].items():
        if digest(name)!=expected: raise ValueError('Prior frozen source changed: '+name)
    candidate = RUN/'experimental_rms_eegnet.npz'
    if digest(candidate)!=result['portable_checks']['artifact_sha256']:
        raise ValueError('Frozen RMS artifact changed')
    baseline = APP/'output/mi_cued_delivery_20261002_final/experimental_eegnet.npz'
    accepted = json.loads((baseline.parent/'acceptance.json').read_text(encoding='utf-8'))
    if digest(baseline)!=accepted['experimental_artifact_sha256']:
        raise ValueError('Frozen old artifact changed')
    with np.load(candidate,allow_pickle=False) as data:
        metadata = json.loads(str(data['metadata'].item()))
    if any(metadata[k] is not False for k in ('control_enabled','promotion_gate_passed','production_eligible')):
        raise ValueError('Candidate must remain unpromoted')
    source = APP/'output/mi_model_comparison_20261001'
    for name,expected in lock['source_cache_sha256'].items():
        if digest(source/name)!=expected: raise ValueError('Frozen source cache changed: '+name)
    bench = APP/'output/accepted_bench_load_20260927/bench_input.npz'
    prior_arm_path = APP/'output/mi_arm_acceptance_20261002_retry1/audit.json'
    prior_arm = json.loads(prior_arm_path.read_text(encoding='utf-8'))
    if not prior_arm['passed'] or digest(bench)!=prior_arm['source_sha256'][str(bench)]:
        raise ValueError('Bench differs from prior accepted156s input')
    with np.load(source/'statistics.npz',allow_pickle=False) as stats:
        indices = np.flatnonzero(np.isin(stats['subjects'],metadata['source_metadata']['fit_people']))[:256]
    waves = np.load(source/'waveforms.npy',allow_pickle=False,mmap_mode='r')
    np.savez_compressed(output/'probe_input.npz',indices=indices,waveforms=np.asarray(waves[indices]))
    capture = APP/'output/mi_live_capture_20261003/full_capture_audit'
    capture_audit = json.loads((capture/'AUDIT.json').read_text(encoding='utf-8'))
    identifiers,real,real_hashes = [],[],{}
    for path in sorted(capture.glob('*.npz')):
        if digest(path)!=capture_audit['file_sha256'][path.name]: raise ValueError('Real waveform changed')
        with np.load(path,allow_pickle=False) as data:
            real.append(data['filtered_uv'].copy())
        identifiers.append(path.stem)
        real_hashes[str(path)] = digest(path)
    if len(real)!=7: raise ValueError('Exactly7 previously saved real windows required')
    np.savez_compressed(output/'real_input.npz',trial_ids=identifiers,waveforms=np.concatenate(real))
    files = {name:RUNTIME/name for name in ASSETS}
    files.update({'mi_eegnet_rms.py':ISOLATED/'mi_eegnet_portable.py',
                  'mi_window_rms.py':ISOLATED/'mi_window_rms.py',
                  'experimental_rms_eegnet.npz':candidate,'experimental_eegnet.npz':baseline,
                  'bench_input.npz':bench,
                  'probe_input.npz':output/'probe_input.npz','real_input.npz':output/'real_input.npz'})
    files['MI_RMS_ARM_PLAN.md'] = APP/'MI_RMS_ARM_PLAN.md'
    files['run_mi_rms_arm_acceptance.py'] = Path(__file__)
    stage = output/'stage'
    stage.mkdir()
    for name,path in files.items(): shutil.copy2(path,stage/name)
    hashes = {str(path):digest(path) for path in files.values()}
    hashes.update(real_hashes)
    hashes.update({str(source/name):digest(source/name) for name in lock['source_cache_sha256']})
    hashes.update({str(path):digest(path) for path in (RUN/'results.json',RUN/'audit.json',RUN/'lock.json',prior_arm_path)})
    return stage,files,hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=APP/'output/mi_rms_arm_acceptance_20261003')
    args = parser.parse_args()
    out = args.output.resolve()
    stage,files,hashes = prepare(out)
    audit = dict(started_at=datetime.now().astimezone().isoformat(),source_sha256=hashes,
                 scope='isolated ARM MI recorded-only, production stays running',passed=False,
                 accuracy_scored=False,model_retrained=False,pl_changed=False,control_enabled=False,
                 numerical_atol=1e-4,filter_atol=1e-6,filter_rtol=1e-7)
    dump(out/'audit.json',audit)
    environment = dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    with (out/'pc.log').open('w',encoding='utf-8') as log:
        result = subprocess.run([sys.executable,'-X','utf8',str(stage/'mi_rms_arm_checks.py'),
            '--mode','functional','--output',str(out/'pc')],env=environment,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode: raise RuntimeError('PC reference failed; inspect pc.log')
    client = connect()
    try:
        client.get_transport().set_keepalive(15)
        audit['before'] = snapshot(client)
        if any(service['ActiveState']!='active' for service in audit['before']['services'].values()):
            raise RuntimeError('Production service not active before isolation test')
        audit['board_kernel'] = command(client,'uname -srmo').strip()
        audit['memory_before'] = command(client,'free -m')
        remote = command(client,'mktemp -d /home/xilinx/mi-rms-arm-XXXXXX').strip()
        if re.fullmatch(r'/home/xilinx/mi-rms-arm-[A-Za-z0-9]+',remote) is None:
            raise ValueError('Unexpected isolated directory')
        audit['remote_directory'] = remote
        with client.open_sftp() as sftp:
            for name in files:
                destination = remote+'/'+name
                sftp.put(str(stage/name),destination)
                if command(client,'sha256sum '+shlex.quote(destination)).split()[0]!=digest(stage/name):
                    raise ValueError('Transfer checksum mismatch: '+name)
        dump(out/'audit.json',audit)
        prefix = 'cd '+shlex.quote(remote)+' && timeout --signal=TERM --kill-after=5s '
        env = 'nice -n 10 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 '+PYTHON+' '
        stream_command(client,prefix+'90s '+env+'-m unittest test_mi_cued test_mi_eegnet_portable test_mi_rms_arm',
                       out/'arm_unit_tests.log',100)
        for mode,limit in (('functional',600),('paced',300)):
            print('RMS_ARM_STAGE',mode,flush=True)
            stream_command(client,prefix+str(limit)+'s '+env+'mi_rms_arm_checks.py --mode '+mode+' --output '+mode,
                           out/(mode+'.log'),limit+15)
            folder = out/mode
            folder.mkdir()
            with client.open_sftp() as sftp:
                sftp.get(remote+'/'+mode+'/suite.json',str(folder/'suite.json'))
                for name in (('old','rms') if mode=='functional' else ('rms',)):
                    local = folder/name
                    local.mkdir()
                    for filename in ('report.json','replay.json','probes.npz','gain_probes.npz','arrays.npz','events.jsonl'):
                        sftp.get(remote+'/'+mode+'/'+name+'/'+filename,str(local/filename))
                    audit[mode+'_'+name+'_parity'] = compare(out/'pc'/name,local)
                    audit[mode+'_'+name+'_gain_parity'] = compare_gain(out/'pc'/name,local)
            audit[mode+'_suite'] = json.loads((folder/'suite.json').read_text(encoding='utf-8'))
            dump(out/'audit.json',audit)
        audit['paced_report'] = json.loads((out/'paced/rms/report.json').read_text(encoding='utf-8'))
        audit['passed'] = bool(audit['paced_report']['summary']['paced_gate_passed']
                               and audit['paced_report']['summary']['lateness_growth_ms']<50)
    except Exception as error:
        audit['failure'] = dict(type=type(error).__name__,message=str(error))
        raise
    finally:
        try:
            audit['after'] = snapshot(client)
            audit['production_files_unchanged'] = audit.get('before',{}).get('hashes')==audit['after']['hashes']
            audit['production_services_unchanged'] = audit.get('before',{}).get('services')==audit['after']['services']
            audit['source_files_unchanged'] = all(digest(path)==expected for path,expected in hashes.items())
            if not all(audit[name] for name in ('production_files_unchanged','production_services_unchanged','source_files_unchanged')):
                audit['passed'] = False
        finally:
            audit['finished_at'] = datetime.now().astimezone().isoformat()
            dump(out/'audit.json',audit)
            client.close()
    if not audit['passed']: raise RuntimeError('Final paced/preservation gate failed')
    print('RMS_ARM_ACCEPTED',audit['remote_directory'],flush=True)


if __name__=='__main__': main()

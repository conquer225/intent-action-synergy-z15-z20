"""Build a private board copy, exercise five tasks and preserve production."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import os

from run_mi_arm_acceptance import (ROOT,RUNTIME,FROZEN,BENCH,PYTHON,digest,dump,
                                   snapshot,stream_command)
from run_soak_stage import connect,command,PROD


def protected_snapshot(client):
    value=snapshot(client)
    probe="""import pathlib,hashlib,json
root=pathlib.Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file() and p.suffix=='.npy'}))
"""
    value['hashes'].update(json.loads(command(client,PYTHON+' -c '+shlex.quote(probe))))
    return value

CHANGED=('cyton_guardianloop.py','soak_service_replay.py','replay_release_audit.py')
EXTRA=('mi_acquisition.py','mi_cued.py','mi_cued_server.py','mi_cued.html','mi_eegnet_portable.py',
       'mi_worker_audit.py',
       'mi_features.py','mi_multitask_replay.py','test_mi_acquisition.py','test_mi_cued.py',
       'test_mi_cued_replay.py','test_mi_eegnet_portable.py','mi_cued_replay.py',
       'mi_cued_acceptance.py','test_mi_cued_acceptance.py')


def mi_check(folder, fault):
    data=json.loads((folder/'mi-report.json').read_text(encoding='utf-8'))[0]
    assert not data['http_errors'],data['http_errors']
    assert data['adapter_error'] is None,data['adapter_error']
    assert data['threads_stopped']
    assert data['final']['result'] is None and data['final']['input_state']=='no_data'
    assert len(data['candidates'])>=6
    assert any(row['elapsed_seconds']>120 for row in data['candidates'])
    assert {row['target'] for row in data['cues']}=={'left','right','rest'}
    assert all(row['target']!='rest' and not row['control_enabled']
               and row['source']=='replay' for row in data['candidates'])
    assert all(row['mi']['source']=='replay' and not row['mi']['production_eligible']
               and not row['mi']['control_enabled'] for row in data['observations'])
    if fault:
        withdrawals=[row for row in data['observations'] if 136<row['elapsed_seconds']<140
                     and row['mi']['result'] is None and row['mi']['state']=='rejected']
        assert withdrawals,'MI withdrawal not observed near pause'
        assert any(row['elapsed_seconds']>140 for row in data['candidates']),'MI new cue did not recover'
    return dict(passed=True,candidates=len(data['candidates']),
                cue_counts=dict(Counter(row['target'] for row in data['cues'])),
                after120_candidates=sum(row['elapsed_seconds']>120 for row in data['candidates']),
                adapter=data['adapter_stats'],final=data['final'],threads_stopped=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline-evidence',type=Path,
                        help='Reuse only a completed identical MI-disabled main-loop baseline')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=False)
    plan=dict(release_id='MI-isolated-five-task-20261002',cases=['full_load','pause_then_reader_fault'],
              numerical_atol=1e-8,numerical_rtol=1e-8,p95_input_age_ms_limit=500,
              max_input_age_ms_limit=3000,seconds=156,input_sha256=digest(BENCH))
    dump(out/'PLAN.json',plan)
    paths=[RUNTIME/name for name in CHANGED+EXTRA]+[RUNTIME/'replay_stage_trace.py',
           Path(__file__),ROOT/'eeg_apps_z15/MI_MULTITASK_PLAN.md',
           ROOT/'eeg_apps_z15/check_frozen_release.py',FROZEN/'experimental_eegnet.npz',BENCH]
    hashes={str(p):digest(p) for p in paths}
    if hashes[str(FROZEN/'experimental_eegnet.npz')]!='178ad7c177adde6fdc939969a40bf25d9e0802d6b230b9127063f14c8402d7e6':
        raise ValueError('Frozen experimental weights changed')
    if plan['input_sha256']!='fb090903dbb523f8bed746ebbe95f4dc26dd70b0c2ab9ad04f716b46fbfcef6f':
        raise ValueError('Original bench changed')
    copies=out/'code_snapshot';copies.mkdir()
    for p in paths:
        if p.suffix in ('.py','.md','.html'):
            shutil.copy2(p,copies/p.name)
    audit=dict(started=datetime.now().isoformat(),passed=False,source_sha256=hashes,
               accuracy_scored=False,production_eligible=False,control_enabled=False)
    dump(out/'audit.json',audit)
    client=connect()
    try:
        audit['before']=protected_snapshot(client)
        assert audit['before']['services']['guardianloop-web.service']['ActiveState']=='active'
        stage=command(client,'mktemp -d /home/xilinx/mi-multitask-XXXXXX').strip()
        if not re.fullmatch('/home/xilinx/mi-multitask-[A-Za-z0-9]+',stage):
            raise ValueError('Unexpected private directory')
        audit['stage']=stage
        installed=out/'installed_runtime';installed.mkdir()
        with client.open_sftp() as sftp:
            for name in sftp.listdir(PROD):
                if Path(name).suffix in ('.py','.json','.npz','.npy'):
                    sftp.get(PROD+'/'+name,str(installed/name))
                    sftp.put(str(installed/name),stage+'/'+name)
            for name in CHANGED+EXTRA+('replay_stage_trace.py',):
                sftp.put(str(RUNTIME/name),stage+'/'+name)
                shutil.copy2(RUNTIME/name,installed/name)
            for path in (FROZEN/'experimental_eegnet.npz',BENCH):
                sftp.put(str(path),stage+'/'+path.name)
            shutil.copy2(FROZEN/'experimental_eegnet.npz',installed/'experimental_eegnet.npz')
        checks=command(client,'cd '+shlex.quote(stage)+' && sha256sum '+
                       ' '.join(CHANGED+EXTRA+('experimental_eegnet.npz','bench_input.npz')))
        expected={Path(path).name:value for path,value in hashes.items()}
        for line in checks.splitlines():
            sha,name=line.split(maxsplit=1)
            assert expected[name]==sha,(name,'Transfer mismatch')
        dump(out/'audit.json',audit)
        prefix='cd '+shlex.quote(stage)+' && timeout -s TERM -k 5 '
        env='env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr '+PYTHON+' '
        stream_command(client,prefix+'90 '+env+'-m unittest test_mi_acquisition test_mi_cued '+
                       'test_mi_cued_replay test_mi_eegnet_portable test_mi_cued_acceptance',
                       out/'arm-tests.log',100)
        audit['runs']={}
        if args.baseline_evidence:
            prior=args.baseline_evidence.resolve()
            old_snapshot=prior/'installed_runtime'
            # MI-only code changes cannot alter the disabled path; every other
            # installed runtime file must be identical before baseline reuse.
            mi_names=set(EXTRA)
            for path in installed.iterdir():
                if path.is_file() and path.name not in mi_names and path.name!='experimental_eegnet.npz':
                    if digest(path)!=digest(old_snapshot/path.name):
                        raise ValueError('Baseline dependency changed: '+path.name)
            baseline_report=json.loads((prior/'baseline/report.json').read_text())
            reference=json.loads((prior/'baseline_reference/full_load/REFERENCE.json').read_text())
            assert reference['passed'] and baseline_report['packets_consumed']==39000
            assert baseline_report['error'] is None and not baseline_report['monitor_errors']
            assert json.loads((prior/'baseline/mi-report.json').read_text())==[]
            shutil.copytree(prior/'baseline',out/'baseline')
            audit['baseline_reused_from']=str(prior)
            audit['runs']['baseline']=dict(baseline_report,reference=reference)
            dump(out/'audit.json',audit)
        for case in ('baseline','full_load','pause_then_reader_fault'):
            if case=='baseline' and args.baseline_evidence:
                continue
            options=''
            if case!='baseline':
                options+=' --mi-experimental-model experimental_eegnet.npz --allow-experimental-mi'
            if case=='pause_then_reader_fault':
                options+=' --pause-at 34000 --pause-seconds 1.2 --reader-fault-after 37000'
            volatile='/dev/shm/'+Path(stage).name+'-'+case
            invoke=prefix+'300 '+env+'mi_multitask_replay.py --input bench_input.npz '+\
                '--input-kind recorded --filter-backend arm --seconds 156 --output '+case+\
                ' --volatile-primary-dir '+volatile+'-primary --volatile-shadow-dir '+volatile+'-shadow'+options
            print('MI_MULTITASK_BEGIN',case,flush=True)
            folder=out/case;folder.mkdir()
            # A declared terminal reader fault exits 1, while full runs must exit 0.
            if case=='pause_then_reader_fault':
                invoke+='; code=$?; test "$code" = 1'
            stream_command(client,invoke,folder/'stdout.log',315)
            with client.open_sftp() as sftp:
                for name in sftp.listdir(stage+'/'+case):
                    if Path(name).suffix in ('.json','.jsonl','.npz','.log'):
                        sftp.get(stage+'/'+case+'/'+name,str(folder/name))
            report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
            audit['runs'][case]=report
            if case!='baseline':
                audit['runs'][case]['mi']=mi_check(folder,case=='pause_then_reader_fault')
            reference_case='full_load' if case=='baseline' else case
            if case=='baseline':
                # The reference checker accepts the fixed existing case names.
                reference_root=out/'baseline_reference';reference_root.mkdir()
                shutil.copytree(installed,reference_root/'installed_runtime')
                shutil.copytree(folder,reference_root/'full_load')
                dump(reference_root/'PLAN.json',plan)
            else:
                reference_root=out
            with (folder/'pc-reference.log').open('w',encoding='utf-8') as log:
                subprocess.run([sys.executable,'-X','utf8',str(ROOT/'eeg_apps_z15/check_frozen_release.py'),
                    '--output',str(reference_root),'--case',reference_case],check=True,
                    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
                    stdout=log,stderr=subprocess.STDOUT)
            audit['runs'][case]['reference']=json.loads(
                (reference_root/reference_case/'REFERENCE.json').read_text(encoding='utf-8'))
            dump(out/'audit.json',audit)
            print('MI_MULTITASK_DONE',case,'packets',report['packets_consumed'],flush=True)
        audit['passed']=True
    except Exception as exc:
        audit['failure']=dict(type=type(exc).__name__,message=str(exc))
        raise
    finally:
        try:
            audit['after']=protected_snapshot(client)
            audit['protected_files_unchanged']=audit.get('before',{}).get('hashes')==audit['after']['hashes']
            audit['web_process_unchanged']=audit.get('before',{}).get('services',{}).get('guardianloop-web.service')==audit['after']['services']['guardianloop-web.service']
            audit['sources_unchanged']=all(digest(path)==value for path,value in hashes.items())
            audit['passed'] &= all(audit[k] for k in ('protected_files_unchanged','web_process_unchanged','sources_unchanged'))
        finally:
            dump(out/'audit.json',audit);client.close()
    if not audit['passed']:
        raise RuntimeError('Final protection checks failed')
    print('MI_MULTITASK_ACCEPTED',stage,flush=True)


if __name__=='__main__':
    main()

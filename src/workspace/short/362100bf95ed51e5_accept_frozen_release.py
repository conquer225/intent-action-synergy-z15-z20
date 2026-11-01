"""156-second installed-release load and failure tests; no hardware writes."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys
import uuid

from deploy_startup import ROOT, PROD, SOURCE, LEDGER, PYTHON, connect, sudo, verify, digest
from run_accepted_bench_load import remote

OUT = ROOT/'eeg_apps_z15/output/final_multitask_acceptance_20261001'
INPUT = ROOT/'eeg_apps_z15/output/accepted_bench_load_20260927/bench_input.npz'


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT)
    OUT=parser.parse_args().output.resolve()
    OUT.mkdir(exist_ok=False)
    ledger = json.loads(LEDGER.read_text(encoding='utf-8'))
    plan = {'release_id': ledger['release_id'], 'input_sha256': hashlib.sha256(INPUT.read_bytes()).hexdigest(),
            'scope': 'non-wear bench recorded replay; not identification accuracy; no actual USB/actuator output',
            'seconds':156, 'samples':39000, 'p95_input_age_ms_limit':500, 'max_input_age_ms_limit':3000,
            'numerical_atol':1e-8, 'numerical_rtol':1e-8,
            'cases': ['full_load', 'pause_then_reader_fault'],
            'fault_pause_at':34000, 'pause_seconds':1.2, 'reader_fault_after':37000,
            'production_runtime_changes':False, 'production_service_restored_in_finally':True}
    save(OUT/'PLAN.json', plan)
    client = connect()
    stopped = False
    try:
        before = verify(client, ledger, 'final_multitask_before.json')
        save(OUT/'before.json', before)
        snapshot = OUT/'installed_runtime'; snapshot.mkdir()
        attempt = uuid.uuid4().hex[:8]
        stage = ledger['stage']+'/final-'+attempt
        remote(client, 'mkdir '+shlex.quote(stage))
        with client.open_sftp() as sftp:
            for name, expected in ledger['release_files'].items():
                sftp.get(PROD+'/'+name, str(snapshot/name))
                if hashlib.sha256((snapshot/name).read_bytes()).hexdigest() != expected:
                    raise RuntimeError('Snapshot mismatch: '+name)
            for name, path in [('input.npz',INPUT), ('soak_service_replay.py',SOURCE/'soak_service_replay.py'),
                               ('replay_release_audit.py',SOURCE/'replay_release_audit.py'),
                               ('replay_stage_trace.py',SOURCE/'replay_stage_trace.py')]:
                sftp.put(str(path),stage+'/'+name)
                if digest(sftp,stage+'/'+name) != hashlib.sha256(path.read_bytes()).hexdigest():
                    raise RuntimeError('Staging mismatch: '+name)
        sudo(client,'systemctl stop guardianloop-cyton.service'); stopped=True
        for case in plan['cases']:
            folder=OUT/case; folder.mkdir()
            remote_output=stage+'/'+case
            args=('--pause-at 34000 --pause-seconds 1.2 --reader-fault-after 37000'
                  if case=='pause_then_reader_fault' else '')
            invocation=('cd '+shlex.quote(stage)+' && timeout -s TERM -k 5 210 env '
                        'PYTHONPATH='+shlex.quote(PROD)+' OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr '
                        +PYTHON+' replay_release_audit.py --input input.npz --input-kind recorded '
                        '--filter-backend arm --seconds 156 --trace-stages --output '+case+' '+args+
                        ' --volatile-primary-dir /dev/shm/gl_final_'+attempt+'_'+case+'_primary'
                        ' --volatile-shadow-dir /dev/shm/gl_final_'+attempt+'_'+case+'_shadow')
            print('BEGIN',case,flush=True)
            _,stdout,stderr=client.exec_command(invocation,timeout=225)
            text=stdout.read().decode(errors='replace')+stderr.read().decode(errors='replace')
            exit_code=stdout.channel.recv_exit_status()
            (folder/'stdout.txt').write_text(text,encoding='utf-8')
            with client.open_sftp() as sftp:
                for name in sftp.listdir(remote_output):
                    if name.endswith(('.json','.jsonl','.npz','.log')):
                        sftp.get(remote_output+'/'+name,str(folder/name))
            report=json.loads((folder/'report.json').read_text())
            save(folder/'execution.json',{'exit_code':exit_code,'stage':stage,'report':report})
            print('DONE',case,json.dumps(report),flush=True)
            if case=='full_load' and exit_code:
                raise RuntimeError('Full-load replay failed')
            if case!='full_load' and (exit_code!=1 or not report['error'] or 'CytonReaderError' not in report['error']):
                raise RuntimeError('Injected reader fault did not follow expected exception path')
    finally:
        if stopped:
            sudo(client,'systemctl start guardianloop-cyton.service')
        client.close()
    client=connect()
    try:
        after=verify(client,ledger,'final_multitask_after.json')
        save(OUT/'after.json',after)
    finally:
        client.close()
    print('CAPTURE_COMPLETE; numerical and coverage checks still required',flush=True)


if __name__=='__main__':
    main()

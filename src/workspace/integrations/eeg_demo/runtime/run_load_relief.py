"""Stage a pinned production copy; run two finite, private ARM replays."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys
import re

import run_live_system as helpers

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'phone_video_upload/output/load_relief_20261007'
STATE=OUT/'state.json'
FORMAL='/home/xilinx/jupyter_notebooks/guardianloop_pynq'


def execute(client,command,root=False):return helpers.execute(client,command,root)


def stage(client):
    if STATE.exists():raise ValueError('Retained stage exists; inspect instead of replacing it')
    manifest=json.loads(execute(client,'cat '+FORMAL+'/release_manifest.json'))
    remote=execute(client,'mktemp -d /home/xilinx/gl-load-relief-20261007-XXXXXX').strip()
    code='''import hashlib,json,pathlib,shutil,sys
source=pathlib.Path(sys.argv[1]);target=pathlib.Path(sys.argv[2]);target.mkdir()
m=json.loads((source/'release_manifest.json').read_text())
for name,expected in m['files'].items():
 if pathlib.Path(name).name!=name:raise ValueError('Unsafe release name')
 path=source/name
 if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('Formal artifact changed')
 shutil.copy2(path,target/name)
shutil.copy2(source/'release_manifest.json',target/'release_manifest.json')
fixture=pathlib.Path('/home/xilinx/gl-media-20261007-314e8796/replay_runtime/bench_input.npz')
if hashlib.sha256(fixture.read_bytes()).hexdigest()!='fb090903dbb523f8bed746ebbe95f4dc26dd70b0c2ab9ad04f716b46fbfcef6f':raise ValueError('Workload changed')
shutil.copy2(fixture,target/'bench_input.npz')
print('PINNED_PRIVATE_COPY_READY')
'''
    print(execute(client,shlex.join([helpers.PYTHON,'-c',code,FORMAL,remote+'/runtime'])))
    names=('soak_service_replay.py','mi_multitask_replay.py','replay_release_audit.py',
           'replay_stage_trace.py','mi_worker_audit.py','async_seed_candidate.py','audited_seed_shadow.py')
    files=[(ROOT/'pynq_guardianloop'/name,remote+'/runtime/'+name) for name in names]
    files += [(ROOT/'pynq_guardianloop/cyton_covariance.py',remote+'/runtime/covariance_array_source.py'),
              (ROOT/'pynq_guardianloop/paired_load_relief.py',remote+'/paired_load_relief.py')]
    with client.open_sftp() as ftp:
        for local,destination in files:
            ftp.put(str(local),destination);ftp.chmod(destination,0o600)
            expected=hashlib.sha256(local.read_bytes()).hexdigest()
            if execute(client,'sha256sum '+shlex.quote(destination)).split()[0]!=expected:
                raise ValueError('Transferred harness differs')
    OUT.mkdir(parents=True,exist_ok=True)
    state=dict(remote=remote,unit=remote.rsplit('/',1)[1],manifest=manifest,
               boot=execute(client,'cat /proc/sys/kernel/random/boot_id').strip())
    STATE.write_text(json.dumps(state,indent=2))
    print(json.dumps(dict(remote=remote,release=manifest['release_id'],files=len(manifest['files']))))


def launch(client,run_id,scheduled_only=False):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,20}',run_id):raise ValueError('Invalid run ID')
    state=json.loads(STATE.read_text());remote=state['remote'];unit=state['unit']+'-'+run_id
    output=remote+'/results-'+run_id
    if execute(client,'systemctl is-active guardianloop-cyton || true').strip()!='active':
        raise ValueError('Expected an active production service before temporary pause')
    if execute(client,'test -e '+shlex.quote(output)+' && echo EXISTS || true').strip():
        raise ValueError('Comparison results already exist')
    local=ROOT/'pynq_guardianloop/paired_load_relief.py'
    with client.open_sftp() as ftp:
        ftp.put(str(local),remote+'/paired_load_relief.py')
        if scheduled_only:
            for name in ('soak_service_replay.py','async_seed_candidate.py','page_scheduled_replay.py'):
                ftp.put(str(ROOT/'pynq_guardianloop'/name),remote+'/runtime/'+name)
            ftp.put(str(ROOT/'guardianloop_system/page_policy.py'),remote+'/runtime/page_policy.py')
    if execute(client,'sha256sum '+remote+'/paired_load_relief.py').split()[0]!=hashlib.sha256(local.read_bytes()).hexdigest():
        raise ValueError('Wrapper transfer mismatch')
    run=dict(unit=unit,output=output,run_id=run_id,cases=['array_scheduled'] if scheduled_only else ['original','array_async'])
    (OUT/'active-run.json').write_text(json.dumps(run,indent=2))
    bound=250 if scheduled_only else 480
    print(execute(client,shlex.join(['systemd-run','--unit='+unit+'-restore','--on-active='+str(bound+10)+'s',
        '--timer-property=AccuracySec=1s','/bin/systemctl','start','guardianloop-cyton']),True))
    print(execute(client,shlex.join(['systemd-run','--unit='+unit,
        '--property=ExecStartPre=/bin/systemctl stop guardianloop-cyton',
        '--property=ExecStopPost=/bin/systemctl start guardianloop-cyton',
        '--property=RuntimeMaxSec='+str(bound)+'s','--property=TimeoutStopSec=5s',
        '--property=KillMode=control-group','--property=MemoryMax=768M','--property=LimitCORE=0',
        'env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',helpers.PYTHON,
        remote+'/paired_load_relief.py','--runtime',remote+'/runtime','--output',output,
        *(['--scheduled-only'] if scheduled_only else [])]),True))


def status(client):
    state=json.loads(STATE.read_text());unit=state['unit']
    if (OUT/'active-run.json').exists():unit=json.loads((OUT/'active-run.json').read_text())['unit']
    print(execute(client,'systemctl show '+unit+' guardianloop-cyton -p MainPID -p ActiveState -p Result'))
    print(execute(client,'journalctl -u '+unit+' -o cat --no-pager -n 8'))


def collect(client):
    state=json.loads(STATE.read_text());remote=state['remote']
    run=json.loads((OUT/'active-run.json').read_text()) if (OUT/'active-run.json').exists() else dict(output=remote+'/results',run_id='first-timeout')
    destination=OUT/run['run_id'];destination.mkdir(exist_ok=True)
    with client.open_sftp() as ftp:
        for name in run.get('cases',('original','array_async')):
            directory=destination/name;directory.mkdir(exist_ok=True)
            for filename in ('report.json','primary_results.json','producer.json','mi-report.json','monitor.jsonl'):
                try:ftp.get(run['output']+'/'+name+'/'+filename,str(directory/filename))
                except FileNotFoundError:continue
        try:ftp.get(run['output']+'/paired-report.json',str(destination/'paired-report.json'))
        except FileNotFoundError:pass
    status(client)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('stage','launch','status','collect'))
    parser.add_argument('--run-id',default='complete-pair')
    parser.add_argument('--scheduled-only',action='store_true')
    args=parser.parse_args();client=helpers.upload.trial.connect('192.168.2.99')
    try:
        if args.action=='launch':launch(client,args.run_id,args.scheduled_only)
        else:globals()[args.action](client)
    finally:client.close()

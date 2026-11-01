"""Explicit private unified-display stage, finite replay, and restoration audit."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import uuid
import re

import stage_server as upload
from stage_media import STATE,PYTHON,update

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'phone_video_upload/output/unified_hdmi_20261007'


def execute(c,command,root=False):return upload.trial.execute(c,command,root=root)


def stage(c,state):
    for unit in ('eeg-page-scheduled','eeg-page-fitted','eeg-page-fitted-official','eeg-page-final',
                 'eeg-page-prescaled','eeg-page-owner-watch','eeg-page-ram-status'):
        active=execute(c,'systemctl show '+state['prefix']+'-'+unit+' -p MainPID --value').strip()
        if active and active!='0':raise ValueError('Do not replace harness files during a replay')
    update(c,state)
    remote=state['remote'];runtime=state['replay_runtime']
    directories=(remote+'/system_runtime',remote+'/system_runtime/guardianloop_system',
                 remote+'/system_runtime/wheelchair_ssvep')
    execute(c,'mkdir -p '+' '.join(shlex.quote(path) for path in directories))
    files=[(ROOT/'guardianloop_system'/name,remote+'/system_runtime/guardianloop_system/'+name)
           for name in ('__init__.py','core.py','page_policy.py','test_core.py','test_page_policy.py')]
    files.append((ROOT/'wheelchair_ssvep/dry_run_bridge.py',remote+'/system_runtime/wheelchair_ssvep/dry_run_bridge.py'))
    files.append((ROOT/'guardianloop_system/page_policy.py',runtime+'/page_policy.py'))
    for name in ('soak_service_replay.py','page_scheduled_replay.py'):
        files.append((ROOT/'pynq_guardianloop'/name,runtime+'/'+name))
    files.append((ROOT/'pynq_guardianloop/cyton_covariance.py',runtime+'/covariance_array_source.py'))
    with c.open_sftp() as sftp:
        for local,target in files:
            sftp.put(str(local),target);sftp.chmod(target,0o600)
            if execute(c,'sha256sum '+shlex.quote(target)).split()[0]!=hashlib.sha256(local.read_bytes()).hexdigest():
                raise ValueError('Unified source transfer changed')
    execute(c,'gcc -O3 -mcpu=cortex-a9 -Wall -Wextra -Werror -fPIC -shared '+shlex.quote(remote+'/frame_fitter.c')+' -o '+shlex.quote(remote+'/frame_fitter.so'))
    command='cd '+shlex.quote(remote)+' && env GL_TEST_EYE_ROOT='+shlex.quote(state['eye_root'])+' PYTHONPATH='+shlex.quote(remote+'/system_runtime:'+runtime+':'+state['eye_root']+'/src')+' '+PYTHON+' -m unittest discover -p test_system_hdmi.py -v'
    command+=' > '+shlex.quote(remote+'/unified-tests.log')+' 2>&1; test_result=$?; cat '+shlex.quote(remote+'/unified-tests.log')+'; exit "$test_result"'
    print(execute(c,'bash -c '+shlex.quote(command)))


def replay(c,state):
    label=args.label;runtime=state['replay_runtime'];remote=state['remote']
    if execute(c,'test -e '+shlex.quote(remote+'/'+label)+' && echo EXISTS || true').strip():
        raise ValueError('Retained output exists; inspect before repeating')
    # The copied production payload remains byte-identical; only the harness is private.
    manifest=json.loads(execute(c,'cat /home/xilinx/jupyter_notebooks/guardianloop_pynq/release_manifest.json'))
    hashes=execute(c,'sha256sum '+' '.join(shlex.quote(runtime+'/'+name) for name in manifest['files']),True)
    if {line.split()[1].rsplit('/',1)[-1]:line.split()[0] for line in hashes.splitlines()}!=manifest['files']:
        raise ValueError('Private production payload changed')
    command=['systemd-run','--unit='+state['prefix']+'-'+label,'--uid=xilinx',
        '--property=RuntimeMaxSec=450s','--property=MemoryMax=512M','--property=LimitCORE=0',
        'env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',PYTHON,runtime+'/mi_multitask_replay.py',
        '--performance-only','--input',runtime+'/bench_input.npz','--output',remote+'/'+label,
        '--seconds','300','--filter-backend','arm','--page-policy-file','/dev/shm/'+state['prefix']+'-system-page.json','--array-covariance',
        '--array-covariance-source',runtime+'/covariance_array_source.py',
        '--mi-experimental-model',runtime+'/experimental_rms_eegnet.npz','--allow-experimental-mi',
        '--mi-web-port','0','--volatile-primary-dir','/dev/shm/'+state['prefix']+'-'+label+'-primary',
        '--volatile-shadow-dir','/dev/shm/'+state['prefix']+'-'+label+'-shadow']
    print(execute(c,shlex.join(command),True))


def display(c,state):
    row=json.loads(execute(c,'tail -n 1 '+state['remote']+'/'+args.label+'/monitor.jsonl'))
    if not(row.get('primary',{}).get('valid') and row.get('primary',{}).get('emotion_valid')):
        raise ValueError('Wait for calibrated primary prediction before joint display')
    current=execute(c,'env XILINX_XRT=/usr '+PYTHON+' -c '+shlex.quote('from pynq import PL; print(PL.bitfile_name)'),True).strip()
    if current!=state['original_overlay']:raise ValueError('Unexpected current PL; no reconfiguration')
    ident='play-system-'+uuid.uuid4().hex[:8]
    config=dict(state,cache=state['remote']+'/'+args.cache,session_id=ident,
        owner_script='media_player.py',hardware_unit=ident+'.service',unified_system=True,
        eye_diagnostic=False,seconds=100,replay_label=args.label)
    path=state['remote']+'/'+ident+'.json'
    with c.open_sftp() as sftp:
        with sftp.open(path,'w') as handle:handle.write(json.dumps(config))
        sftp.chmod(path,0o600)
    print(execute(c,shlex.join(['systemd-run','--unit='+ident+'-restore','--on-active=150s',
        '--timer-property=AccuracySec=1s','env','XILINX_XRT=/usr',PYTHON,
        state['remote']+'/playback_recovery.py','--state',path]),True))
    print(execute(c,shlex.join(['systemd-run','--unit='+ident,'--property=TimeoutStopSec=infinity',
        '--property=KillMode=process','--property=LimitCORE=0',
        'env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',PYTHON,state['remote']+'/media_player.py',
        '--state',path]),True))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'launch.json').write_text(json.dumps(dict(session_id=ident,primary=row,config_path=path)))
    print('UNIFIED_PRIVATE_DISPLAY_STARTED',ident,flush=True)


def status(c,state):
    print(execute(c,'systemctl show '+state['prefix']+'-'+args.label+' -p MainPID -p ActiveState -p Result -p ExecMainStatus; tail -n 1 '+state['remote']+'/'+args.label+'/monitor.jsonl'))


def collect(c,state):
    OUT.mkdir(parents=True,exist_ok=True);remote=state['remote']
    with c.open_sftp() as sftp:
        for name in sftp.listdir(remote):
            if name.startswith('play-system-') and name.endswith('-report.json'):
                sftp.get(remote+'/'+name,str(OUT/name))
        ram_status='/dev/shm/'+state['prefix']+'-player-status.json'
        status_file=ram_status if ram_status.rsplit('/',1)[1] in sftp.listdir('/dev/shm') else remote+'/player_status.json'
        with sftp.open(status_file) as handle:
            player_status=json.load(handle)
        session_id=player_status.get('session_id','')
        if re.fullmatch(r'play-system-[0-9a-f]{8}',session_id):
            (OUT/(session_id+'-status.json')).write_text(json.dumps(player_status,indent=2))
        target=OUT/args.label;target.mkdir(exist_ok=True)
        for name in sftp.listdir(remote+'/'+args.label):
            if name.endswith(('.json','.jsonl','.log')):
                sftp.get(remote+'/'+args.label+'/'+name,str(target/name))
    manifest=json.loads(execute(c,'cat /home/xilinx/jupyter_notebooks/guardianloop_pynq/release_manifest.json'))
    hashes=execute(c,'sha256sum '+' '.join(shlex.quote('/home/xilinx/jupyter_notebooks/guardianloop_pynq/'+name) for name in manifest['files']),True)
    audit=dict(release_unchanged={line.split()[1].rsplit('/',1)[-1]:line.split()[0] for line in hashes.splitlines()}==manifest['files'],
        release_files=len(manifest['files']),protected_unchanged=upload.trial.protected(c)==state['before_hashes'],
        services=upload.trial.services(c),before_services=state['before_services'],audio_output=False,physical_control=False,
        pl=execute(c,'env XILINX_XRT=/usr '+PYTHON+' -c '+shlex.quote('from pynq import PL; print(PL.bitfile_name)'),True).strip())
    audit['pl_restored']=audit['pl']==state['original_overlay']
    (OUT/'final_audit.json').write_text(json.dumps(audit,indent=2))
    print(json.dumps(audit))
    for path in OUT.glob('play-system-*-report.json'):
        report=json.loads(path.read_text())
        print(json.dumps(dict(session=path.stem,**{key:report.get(key) for key in
            ('fps','frames','wall_s','video_active_s','minimum_full_second_frames','meets_16fps','errors',
             'original_restored','buffers_released','page_transitions','display_overlay_loads')}),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('stage','replay','display','status','collect'))
    parser.add_argument('--label',default='eeg-page-scheduled')
    parser.add_argument('--cache',choices=('fixture60compact','fixture60central'),default='fixture60compact')
    args=parser.parse_args();state=json.loads(STATE.read_text());client=upload.trial.connect('192.168.2.99')
    if not re.fullmatch(r'eeg-[a-z0-9-]{1,40}',args.label):raise ValueError('Invalid isolated workload label')
    try:globals()[args.action](client,state)
    finally:client.close()

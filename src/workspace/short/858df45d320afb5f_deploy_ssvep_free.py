"""Reversible ARM-only free-choice SSVEP delivery; preserve MI, models and PL."""
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

from run_soak_stage import connect, command
from run_ssvep_backlog_replay import checked
from run_mi_arm_acceptance import digest, dump, snapshot, stream_command

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'pynq_guardianloop'
OUT = ROOT/'eeg_apps_z15/output/ssvep_free_20261003'
FORMAL = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'
CHANGED = ('ssvep_free.py','ssvep_free.html','ssvep_cue_runtime.py','guardianloop_web.py')
TESTS = ('test_ssvep_free','test_ssvep_cue_runtime','test_ssvep_cued',
         'test_mi_formal_entry','test_guardianloop_startup')
RELEASE_ID = 'guardianloop-fixed8-mi-ssvep-free-20261003'
PROFILE = 'free'


def get(client, path):
    return json.loads(command(client,'curl -fsS --max-time 3 http://127.0.0.1:9102'+path))


def idle(client):
    mi, cue, free, recording = (get(client,path) for path in
                         ('/api/mi-cue','/api/ssvep-cue','/api/ssvep-free','/api/recording'))
    if any(s.get('state') in ('active','awaiting_presentation') for s in (mi,cue,free)):
        raise RuntimeError('Active human trial: refuse interruption')
    if recording.get('recording',{}).get('state')=='recording':
        raise RuntimeError('Active recording: refuse interruption')
    expected_model = '363daf3b68da6e80495319052447ec83e06b9e3e327a1bd0ff9e6023a5b54221'
    if mi.get('candidate_model',{}).get('sha256') != expected_model and not (
            PROFILE=='wait-replay' and mi.get('reason')=='mi_backend_unavailable'
            and command(client,'sha256sum '+FORMAL+'/experimental_rms_eegnet.npz').split()[0]==expected_model):
        raise RuntimeError('MI model changed since user acceptance')
    return dict(mi=mi,cue=cue,free=free,recording=recording)


def prepare(client):
    current = idle(client)
    before = snapshot(client)
    OUT.mkdir(exist_ok=False)
    package = OUT/'package'
    runtime = package/'runtime'
    runtime.mkdir(parents=True)
    (package/'rollback_original').mkdir()
    with client.open_sftp() as sftp:
        with sftp.open(FORMAL+'/release_manifest.json') as stream:
            old = json.load(stream)
        for name, checksum in old['files'].items():
            if Path(name).name != name:
                raise ValueError('Unexpected nested release member')
            sftp.get(FORMAL+'/'+name,str(runtime/name))
            if digest(runtime/name) != checksum:
                raise ValueError('Installed manifest mismatch: '+name)
            before['hashes'][FORMAL+'/'+name] = checksum
        # Root configuration is protected independently from the app manifest.
        for path in ('/etc/default/guardianloop-mi.json',
                     '/etc/systemd/system/guardianloop-startup.service'):
            before['hashes'][path] = command(client,'sha256sum '+shlex.quote(path)).split()[0]
        targets = {}
        for name in (*CHANGED,'release_manifest.json'):
            path = FORMAL+'/'+name
            checksum = before['hashes'].get(path)
            if checksum:
                sftp.get(path,str(package/'rollback_original'/name))
                if digest(package/'rollback_original'/name) != checksum:
                    raise ValueError('Backup checksum mismatch')
            else:
                try:sftp.stat(path)
                except FileNotFoundError:pass
                else:raise ValueError('Untracked target exists: '+name)
            targets[path] = dict(old_sha256=checksum, original='rollback_original/'+name if checksum else None,
                                 replacement='runtime/'+name,new_sha256=None)
    for name in CHANGED:
        shutil.copy2(SOURCE/name,runtime/name)
    manifest = dict(old, release_id=RELEASE_ID,
        previous_release_id=old['release_id'],
        ssvep_free=dict(enabled=True,experimental=True,channels=['O1','O2'],frequencies=[8,10,12,14],
                        idle_classifier_validated=False,control_enabled=False),
        files={p.name:digest(p) for p in runtime.iterdir() if p.is_file() and p.name!='release_manifest.json'})
    dump(runtime/'release_manifest.json',manifest)
    for row in targets.values():row['new_sha256']=digest(package/row['replacement'])
    dump(package/'transaction.json',dict(targets=targets,protected=before['hashes'],
        runtime_sha256={p.name:digest(p) for p in runtime.iterdir() if p.is_file()}))
    shutil.copy2(SOURCE/'mi_rms_bundle.py',package/'mi_rms_bundle.py')
    for name in TESTS:shutil.copy2(SOURCE/(name+'.py'),runtime/(name+'.py'))
    shutil.copy2(SOURCE/'test_ssvep_free_browser.js',runtime/'test_ssvep_free_browser.js')
    remote=command(client,'mktemp -d /home/xilinx/ssvep-free-XXXXXX').strip()
    if not re.fullmatch(r'/home/xilinx/ssvep-free-[A-Za-z0-9]+',remote):
        raise ValueError('Unexpected private directory')
    with client.open_sftp() as sftp:
        for folder in ('runtime','rollback_original'):sftp.mkdir(remote+'/'+folder)
        for path in package.rglob('*'):
            if path.is_file():
                target=remote+'/'+path.relative_to(package).as_posix()
                sftp.put(str(path),target)
                if command(client,'sha256sum '+shlex.quote(target)).split()[0]!=digest(path):
                    raise ValueError('Transfer mismatch')
    audit=dict(phase='prepared',profile=PROFILE,before=before,previous_state=current,remote=remote,
               created_at=datetime.now().astimezone().isoformat(),pl_changed=False,
               board_rebooted=False,targets=list(targets))
    dump(OUT/'deployment.json',audit)
    print('PREPARED',remote,flush=True)


def test(client,audit):
    runtime=OUT/'package/runtime'
    for name in ('pc_tests.log','arm_tests.log','browser_tests.log'):
        log=OUT/name
        if log.exists():
            backup=OUT/(log.stem+'-attempt-'+str(len(list(OUT.glob(log.stem+'-attempt-*')))+1)+'.log')
            shutil.copy2(log,backup)
    with client.open_sftp() as sftp:
        for name in TESTS:
            filename=name+'.py'
            shutil.copy2(SOURCE/filename,runtime/filename)
            sftp.put(str(runtime/filename),audit['remote']+'/runtime/'+filename)
        shutil.copy2(SOURCE/'test_ssvep_free_browser.js',runtime/'test_ssvep_free_browser.js')
        sftp.put(str(runtime/'test_ssvep_free_browser.js'),audit['remote']+'/runtime/test_ssvep_free_browser.js')
        if PROFILE=='free-study':
            shutil.copy2(SOURCE/'audit_ssvep_study.py',runtime/'audit_ssvep_study.py')
            sftp.put(str(runtime/'audit_ssvep_study.py'),audit['remote']+'/runtime/audit_ssvep_study.py')
    with (OUT/'pc_tests.log').open('w',encoding='utf-8') as log:
        subprocess.run([sys.executable,'-X','utf8','-m','unittest',*TESTS],cwd=runtime,
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    with (OUT/'browser_tests.log').open('w',encoding='utf-8') as log:
        subprocess.run(['node','test_ssvep_free_browser.js'],cwd=runtime,
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    # Unit fixtures use RAM, avoiding unrelated SD fsync latency under live acquisition.
    invocation='cd '+shlex.quote(audit['remote']+'/runtime')+' && env TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 150s '+PYTHON+' -m unittest '+' '.join(TESTS)
    stream_command(client,invocation,OUT/'arm_tests.log',155)
    audit['phase']='tested'
    dump(OUT/'deployment.json',audit)


def refresh(client,audit):
    if audit['phase'] not in ('prepared','tested'):
        raise ValueError('Only an uninstalled stage may be refreshed')
    package=OUT/'package'
    runtime=package/'runtime'
    for name in CHANGED:
        shutil.copy2(SOURCE/name,runtime/name)
    manifest=json.loads((runtime/'release_manifest.json').read_text(encoding='utf-8'))
    manifest['files']={name:digest(runtime/name) for name in manifest['files']}
    dump(runtime/'release_manifest.json',manifest)
    ledger=json.loads((package/'transaction.json').read_text(encoding='utf-8'))
    for row in ledger['targets'].values():
        row['new_sha256']=digest(package/row['replacement'])
    ledger['runtime_sha256']={name:digest(runtime/name) for name in ledger['runtime_sha256']}
    dump(package/'transaction.json',ledger)
    with client.open_sftp() as sftp:
        for name in (*CHANGED,'release_manifest.json'):
            sftp.put(str(runtime/name),audit['remote']+'/runtime/'+name)
        sftp.put(str(package/'transaction.json'),audit['remote']+'/transaction.json')
    audit['phase']='prepared'
    dump(OUT/'deployment.json',audit)
    print('REFRESHED: stage requires another test run',flush=True)


def install(client,audit):
    if audit['phase']!='tested':raise ValueError('Stage tests must pass')
    idle(client)
    remote=shlex.quote(audit['remote'])
    invoke=PYTHON+' '+remote+'/mi_rms_bundle.py '
    print(checked(client,invoke+'check --bundle '+remote,sudo=True),flush=True)
    print(checked(client,invoke+'install --bundle '+remote,sudo=True),flush=True)
    audit['phase']='installed'
    dump(OUT/'deployment.json',audit)


def verify(client,audit):
    deadline=time.monotonic()+45
    while True:
        after=snapshot(client)
        try:
            statuses={path:get(client,path) for path in ('/api/mi-cue','/api/ssvep-cue','/api/ssvep-free','/api/ssvep-shadow')}
            available=statuses['/api/ssvep-free'].get('state')!='unavailable' and statuses['/api/mi-cue'].get('state')!='unavailable'
        except RuntimeError:
            available=False
        if available and all(s['ActiveState']=='active' for s in after['services'].values()):break
        if time.monotonic()>=deadline:raise RuntimeError('Services did not become ready after deployment')
        time.sleep(1)
    after=snapshot(client)
    ledger=json.loads((OUT/'package/transaction.json').read_text(encoding='utf-8'))
    for path, checksum in ledger['protected'].items():
        expected=ledger['targets'].get(path,{}).get('new_sha256',checksum)
        actual=command(client,'sha256sum '+shlex.quote(path)).split()[0]
        if actual!=expected:raise ValueError('Unexpected runtime modification: '+path)
    for path,row in ledger['targets'].items():
        if command(client,'sha256sum '+shlex.quote(path)).split()[0]!=row['new_sha256']:
            raise ValueError('Installed target mismatch')
    for unit,state in after['services'].items():
        if state['ActiveState']!='active':raise ValueError('Inactive service: '+unit)
    statuses={path:get(client,path) for path in ('/api/mi-cue','/api/ssvep-cue','/api/ssvep-free','/api/ssvep-shadow')}
    if statuses['/api/ssvep-free']['state'] not in ('idle','stopped'):raise ValueError('Free experiment started unexpectedly')
    if statuses['/api/mi-cue']['candidate_model']['sha256']!='363daf3b68da6e80495319052447ec83e06b9e3e327a1bd0ff9e6023a5b54221':
        raise ValueError('MI model mismatch')
    pages={path:len(command(client,'curl -fsS --max-time 3 http://127.0.0.1:9102'+path))
           for path in ('/','/mi-cued','/ssvep-cued','/ssvep-free')}
    manifest_check="import pathlib,json;from guardianloop_startup import verify_files;r=pathlib.Path('.');print(verify_files(r,json.loads((r/'release_manifest.json').read_text())))"
    verified=command(client,'cd '+FORMAL+' && '+PYTHON+' -c '+shlex.quote(manifest_check))
    dump(OUT/'postflight.json',dict(after=after,statuses=statuses,page_bytes=pages,
        verified_manifest_files=verified.strip(),pl_changed=False,models_changed=False,
        physical_controls=False,human_accuracy_measured=False))
    audit['phase']='verified'
    dump(OUT/'deployment.json',audit)
    print(json.dumps(dict(phase='verified',pages=pages,mi_input=statuses['/api/mi-cue']['input_state'],
                         free_state=statuses['/api/ssvep-free']['state'],manifest_files=verified.strip())),flush=True)


def soak(client,audit):
    if PROFILE not in ('wait-replay','free-study') or audit['phase']!='verified':
        raise ValueError('No-data soak requires the verified wait deployment')
    probe="""import json,subprocess,urllib.request,pathlib
data={}
for p in ('ssvep-cue','ssvep-free','mi-cue'):
 with urllib.request.urlopen('http://127.0.0.1:9102/api/'+p,timeout=3) as r:data[p]=json.load(r)
data['units']=subprocess.check_output(['systemctl','show','guardianloop-cyton.service','guardianloop-web.service',
 '-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState','-p','SubState'],text=True)
data['boot_id']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
print(json.dumps(data))
"""
    rows=[];began=time.monotonic()
    for index in range(21):
        data=json.loads(command(client,PYTHON+' -c '+shlex.quote(probe)))
        data['elapsed_seconds']=round(time.monotonic()-began,3);rows.append(data)
        if index%5==0:print('NO-DATA SOAK',index+1,'/ 21',flush=True)
        if index<20:time.sleep(3)
    stable=all(r['units']==rows[0]['units'] and r['boot_id']==rows[0]['boot_id'] for r in rows)
    waiting=all(r[p].get('input',{}).get('state')=='no_data' and
                r[p].get('input',{}).get('reason')=='waiting_for_cyton' and
                r[p].get('accepted') is False and r[p].get('result') is None
                for r in rows for p in ('ssvep-cue','ssvep-free'))
    mi_safe=all(r['mi-cue'].get('input_state')=='no_data' and r['mi-cue'].get('result') is None
                and r['mi-cue'].get('control_enabled') is False for r in rows)
    report=dict(rows=rows,duration_seconds=rows[-1]['elapsed_seconds'],
        stable_pid_and_restart_count=stable,ssvep_waiting_without_results=waiting,
        mi_no_data_without_results=mi_safe,passed=stable and waiting and mi_safe,
        cyton_switched_on=False,real_radio_resume_verified=False)
    dump(OUT/'no_data_soak.json',report)
    if not report['passed']:raise RuntimeError('No-data soak failed; inspect recorded evidence')
    print('NO-DATA SOAK PASS: stable processes; no stale results',flush=True)


def main():
    global OUT, CHANGED, TESTS, RELEASE_ID, PROFILE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','refresh','test','install','verify','soak','rollback'))
    parser.add_argument('--profile',choices=('free','reader-repair','usability','wait-replay','free-study'),default='free')
    args=parser.parse_args()
    PROFILE=args.profile
    if PROFILE=='reader-repair':
        OUT=ROOT/'eeg_apps_z15/output/ssvep_reader_repair_20261003'
        RELEASE_ID='guardianloop-fixed8-mi-ssvep-reader-20261003'
        CHANGED=(*CHANGED,'cyton_reader_sink.py','ssvep_acquisition.py','cyton_guardianloop.py','mi_acquisition.py')
        TESTS=(*TESTS,'test_ssvep_acquisition','test_mi_reader_tap','test_mi_cued','test_cyton_reader_faults')
    elif PROFILE=='usability':
        OUT=ROOT/'eeg_apps_z15/output/ssvep_usability_20261003'
        RELEASE_ID='guardianloop-fixed8-ssvep-usability-20261003'
        CHANGED=(*CHANGED,'ssvep_recording.py','cyton_trial_recorder.py','cyton_guardianloop.py')
        TESTS=(*TESTS,'test_ssvep_recording','test_ssvep_acquisition','test_mi_reader_tap',
               'test_mi_cued','test_cyton_reader_faults','test_cyton_trial_recorder')
    elif PROFILE=='wait-replay':
        OUT=ROOT/'eeg_apps_z15/output/ssvep_wait_deployment_20261003'
        RELEASE_ID='guardianloop-fixed8-ssvep-wait-20261003'
        CHANGED=('cyton_guardianloop.py','guardianloop_acquisition.py','ssvep_shadow.py',
                 'guardianloop_web.py','ssvep_free.html')
        TESTS=(*TESTS,'test_ssvep_shadow','test_ssvep_recording','test_ssvep_acquisition',
               'test_mi_reader_tap','test_mi_cued','test_cyton_reader_faults','test_cyton_trial_recorder',
               'test_cyton_wait_service')
    elif PROFILE=='free-study':
        OUT=ROOT/'eeg_apps_z15/output/ssvep_free_study_20261003'
        RELEASE_ID='guardianloop-fixed8-ssvep-study-20261003'
        CHANGED=('ssvep_free.py','ssvep_free.html','ssvep_cue_runtime.py','ssvep_recording.py',
                 'cyton_trial_recorder.py','ssvep_study.py')
        TESTS=(*TESTS,'test_ssvep_shadow','test_ssvep_recording','test_ssvep_acquisition',
               'test_mi_reader_tap','test_mi_cued','test_cyton_reader_faults','test_cyton_trial_recorder',
               'test_cyton_wait_service','test_ssvep_study')
    client=connect()
    try:
        if args.action=='prepare':prepare(client);return
        audit=json.loads((OUT/'deployment.json').read_text(encoding='utf-8'))
        if args.action=='rollback':
            print(checked(client,PYTHON+' '+shlex.quote(audit['remote']+'/mi_rms_bundle.py')+
                          ' rollback --bundle '+shlex.quote(audit['remote']),sudo=True))
        else:globals()[args.action](client,audit)
    finally:client.close()


if __name__=='__main__':main()

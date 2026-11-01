"""Stage, test and reversibly update only ARM SSVEP window ownership."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

from run_soak_stage import ROOT, PROD, connect, command
from run_mi_arm_acceptance import PYTHON, digest, dump, stream_command
from run_mi_multitask import protected_snapshot
from deploy_ssvep_rail_coalesce import sudo

OUT = ROOT/'eeg_apps_z15/output/ssvep_producer_cue_20261002'
SOURCE = ROOT/'pynq_guardianloop'
CHANGED = ('cyton_guardianloop.py', 'guardianloop_web.py', 'ssvep_shadow.py', 'ssvep_cued.py')
NEW = 'ssvep_cue_runtime.py'
TESTS = ('test_ssvep_cued', 'test_ssvep_cue_runtime', 'test_ssvep_shadow',
         'test_ssvep_core', 'test_ssvep_cache', 'test_ssvep_stream', 'test_mi_formal_entry',
         'test_guardianloop_startup', 'test_seed_shadow_web', 'test_seed_shadow',
         'test_seed_quality_runtime', 'test_cyton_reader_faults', 'test_small_batch')
RAW_RECORDING_PROFILE = False


def ledger():
    return json.loads((OUT/'deployment.json').read_text(encoding='utf-8'))


def backend_probe(client):
    probe = '''import json,urllib.request,pathlib,subprocess
urls={}
for path in ('/api/ssvep-cue','/api/ssvep-shadow','/api/mi-cue','/api/recording','/api/status'):
 with urllib.request.urlopen('http://127.0.0.1:9102'+path,timeout=5) as reply:
  item=json.load(reply)
 if path=='/api/status':item={'stale':item['stale'],'startup':item['system']['startup'],'state':item['fatigue'].get('state')}
 if path=='/api/ssvep-shadow':item={k:item['live'].get(k) for k in ('source','state','valid','packets_seen','sequence_gaps')}
 urls[path]=item
listeners=[]
for name in ('tcp','tcp6'):
 for line in pathlib.Path('/proc/net/'+name).read_text().splitlines()[1:]:
  parts=line.split()
  if parts[3]=='0A' and int(parts[1].split(':')[1],16)==9105:listeners.append(parts[1])
print(json.dumps({'urls':urls,'backend_listeners':listeners,'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 'units':subprocess.check_output(['systemctl','show','guardianloop-cyton','guardianloop-web','-p','MainPID','-p','NRestarts','-p','ActiveState','-p','ExecStart']).decode()}))
'''
    return json.loads(command(client,'python3 -c '+shlex.quote(probe)))


def audit_configs(client):
    probe = '''import pathlib,hashlib,json
paths=[pathlib.Path('/etc/default/guardianloop-mi.json')]
for name in ('guardianloop-cyton.service.d','guardianloop-web.service.d'):
 p=pathlib.Path('/etc/systemd/system')/name
 if p.is_dir():paths.extend(x for x in p.iterdir() if x.is_file())
print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}))
'''
    return json.loads(command(client,'python3 -c '+shlex.quote(probe)))


def require_idle(probe):
    cue = probe['urls']['/api/ssvep-cue']
    recording = probe['urls']['/api/recording'].get('recording', {})
    if cue.get('state') in ('active','awaiting_presentation') or recording.get('state')=='recording':
        raise ValueError('Active stimulus/recording; do not interrupt it')
    if '--ssvep-cue-log' in probe['units']:
        raise ValueError('Installed web unit uses the retired cue-log CLI; inspect its migration')
    if probe['urls']['/api/mi-cue'].get('enabled') is not False:
        raise ValueError('Unexpected active MI; preserve the current experiment')


def stage(client):
    OUT.mkdir(exist_ok=False)
    before = protected_snapshot(client)
    configs = audit_configs(client)
    probe = backend_probe(client)
    require_idle(probe)
    if probe['backend_listeners'] and not RAW_RECORDING_PROFILE:
        raise ValueError('9105 already occupied; do not replace an unrelated server')
    if RAW_RECORDING_PROFILE and (probe['backend_listeners'] != ['0100007F:2391']
            or probe['urls']['/api/ssvep-cue'].get('state_owner') != 'acquisition'):
        raise ValueError('Raw recording update requires the already verified cue owner')
    dump(OUT/'before.json',dict(snapshot=before,configs=configs,probe=probe))
    original = OUT/'original';original.mkdir()
    runtime = OUT/'runtime';runtime.mkdir()
    location = command(client,'mktemp -d /home/xilinx/ssvep-producer-XXXXXX').strip()
    if not location.startswith('/home/xilinx/ssvep-producer-') or not Path(location).name.replace('-','').isalnum():
        raise ValueError('Unexpected isolated directory')
    with client.open_sftp() as s:
        s.get(PROD+'/release_manifest.json',str(original/'release_manifest.json'))
        old=json.loads((original/'release_manifest.json').read_text())
        for name,value in old['files'].items():
            s.get(PROD+'/'+name,str(original/name))
            if digest(original/name)!=value:
                raise ValueError('Production manifest mismatch: '+name)
            shutil.copy2(original/name,runtime/name)
        if NEW is not None and (runtime/NEW).exists():
            raise ValueError('New module already exists in release')
        changed_names=CHANGED+((NEW,) if NEW is not None else ())
        for name in changed_names:shutil.copy2(SOURCE/name,runtime/name)
        manifest=dict(old,release_id=('guardianloop-fixed-cap-ssvep-raw-sync-20261002'
            if RAW_RECORDING_PROFILE else 'guardianloop-fixed-cap-ssvep-producer-20261002'),
            previous_release_id=old['release_id'],
            ssvep_cue=dict(state_owner='acquisition',observation_mode='producer_callbacks',
                          required_consecutive_windows=3,window_samples=500,hop_samples=50,
                          control_enabled=False,live_accuracy_verified=False),
            files={p.name:digest(p) for p in sorted(runtime.iterdir()) if p.is_file()})
        if RAW_RECORDING_PROFILE:
            manifest['ssvep_cue']['raw_recording_supported']=True
            manifest['ssvep_cue']['raw_alignment']='packet_index_and_usb_receive_monotonic_not_optical'
        dump(runtime/'release_manifest.json',manifest)
        for p in runtime.iterdir():s.put(str(p),location+'/'+p.name)
        for name in CHANGED+('release_manifest.json',):
            s.put(str(original/name),location+'/'+name+'.original')
        for name in TESTS:
            origin=SOURCE/(name+'.py')
            if not origin.exists():origin=ROOT/'eeg_apps_z15'/(name+'.py')
            s.put(str(origin),location+'/'+name+'.py')
    plan=dict(stage=location,phase='staging',started_pc_local=datetime.now().isoformat(),
              before=before,configs=configs,boot_id=probe['boot_id'],manifest=manifest,
              hashes={p.name:digest(p) for p in runtime.iterdir()},
              changed=list(changed_names)+['release_manifest.json'],
              original_existing=list(CHANGED)+['release_manifest.json'],
              models_changed=False,thresholds_changed=False,pl_changed=False,boot_changed=False)
    dump(OUT/'deployment.json',plan)
    local = subprocess.run([str(ROOT/'eeg_apps_z15/.venv-mi/Scripts/python.exe'),'-X','utf8',
                            '-m','unittest',*TESTS],cwd=SOURCE,
                           env=dict(os.environ, PYTHONPATH=str(SOURCE)+';'+str(ROOT/'eeg_apps_z15')),
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=55)
    (OUT/'local-tests.log').write_bytes(local.stdout)
    if local.returncode:raise RuntimeError('Local tests failed; see local-tests.log')
    complete_stage(client, plan)


def complete_stage(client, plan):
    if plan['phase']!='staging':raise ValueError('Stage is not awaiting tests')
    result=(OUT/'local-tests.log').read_text().rstrip().splitlines()[-1]
    if result != 'OK' and not (result.startswith('OK (skipped=') and result.endswith(')')):
        raise ValueError('Local suite did not pass')
    invoke='cd '+shlex.quote(plan['stage'])+' && timeout --kill-after=3s 50s env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr '+PYTHON
    for group,names in (('cue',TESTS[:6]),('regression',TESTS[6:])):
        log=OUT/('arm-tests-'+group+'.log')
        if log.exists():raise ValueError('Preserve existing grouped test log: '+str(log))
        stream_command(client,invoke+' -m unittest '+' '.join(names),log,55)
    check='''import pathlib,json
from guardianloop_startup import verify_files
root=pathlib.Path('.')
print(json.dumps({'verified_files':verify_files(root,json.loads((root/'release_manifest.json').read_text())),'pl_called':False}))
'''
    verified=json.loads(command(client,invoke+' -c '+shlex.quote(check)))
    if verified['verified_files']!=len(plan['manifest']['files']):raise ValueError('File verification mismatch')
    if protected_snapshot(client)['hashes']!=plan['before']['hashes'] or audit_configs(client)!=plan['configs']:
        raise ValueError('Formal files changed during staging')
    plan.update(phase='stage_passed',stage_verified=verified)
    dump(OUT/'deployment.json',plan)
    print('STAGE_PASSED',plan['stage'],flush=True)


def rollback(client,plan):
    with client.open_sftp() as s:
        for name in plan['changed']:
            try:actual=hashlib.sha256(s.open(PROD+'/'+name,'rb').read()).hexdigest()
            except FileNotFoundError:continue
            previous=plan['before']['hashes'].get(PROD+'/'+name)
            if actual not in (plan['hashes'][name],previous):
                raise ValueError('Foreign change; rollback refused: '+name)
    sudo(client,'systemctl stop guardianloop-web.service guardianloop-cyton.service')
    originals=plan.get('original_existing',list(CHANGED)+['release_manifest.json'])
    for name in originals:
        sudo(client,'install -m 644 '+shlex.quote(plan['stage']+'/'+name+'.original')+' '+shlex.quote(PROD+'/'+name))
    for name in plan['changed']:
        if name not in originals:
            sudo(client,'if test -f '+shlex.quote(PROD+'/'+name)+'; then mv '+shlex.quote(PROD+'/'+name)+' '+shlex.quote(plan['stage']+'/'+name+'.withdrawn')+'; fi')
    sudo(client,'systemctl start guardianloop-web.service guardianloop-cyton.service')
    plan['phase']='rolled_back';dump(OUT/'deployment.json',plan)


def activate(client):
    plan=ledger()
    if plan['phase']!='stage_passed':raise ValueError('Stage has not passed')
    require_idle(backend_probe(client))
    if protected_snapshot(client)['hashes']!=plan['before']['hashes'] or audit_configs(client)!=plan['configs']:
        raise ValueError('Formal state changed after stage')
    with client.open_sftp() as s:
        for name,value in plan['hashes'].items():
            if hashlib.sha256(s.open(plan['stage']+'/'+name,'rb').read()).hexdigest()!=value:
                raise ValueError('Stage changed: '+name)
    plan['phase']='installing';dump(OUT/'deployment.json',plan)
    try:
        sudo(client,'systemctl stop guardianloop-web.service guardianloop-cyton.service')
        for name in plan['changed']:
            sudo(client,'install -m 644 '+shlex.quote(plan['stage']+'/'+name)+' '+shlex.quote(PROD+'/'+name))
        sudo(client,'systemctl start guardianloop-web.service guardianloop-cyton.service')
        plan['phase']='installed';dump(OUT/'deployment.json',plan)
        verify(client)
    except Exception:
        # Restore only files whose hashes are still ours or the pre-update originals.
        rollback(client,plan)
        raise


def verify(client):
    plan=ledger()
    probe=None
    for _ in range(10):
        try:
            probe=backend_probe(client)
            if probe['urls']['/api/ssvep-cue'].get('state_owner')=='acquisition' and probe['backend_listeners']:
                break
        except (RuntimeError,ValueError):pass
        time.sleep(1)
    if probe is None or not probe['backend_listeners']:raise ValueError('Acquisition cue server not ready')
    cue=probe['urls']['/api/ssvep-cue']
    if (cue.get('observation_mode')!='producer_callbacks' or cue.get('state')!='idle'
            or cue.get('accepted') is not False or cue.get('control_enabled') is not False):
        raise ValueError('Cue ownership/idle safety mismatch')
    if probe['backend_listeners']!=['0100007F:2391']:raise ValueError('Cue backend must bind only loopback')
    if (plan['manifest']['ssvep_cue'].get('raw_recording_supported')
            and (cue.get('raw_recording_supported') is not True or cue.get('raw_recording') is not None)):
        raise ValueError('Raw recording capability/idle state mismatch')
    if probe['boot_id']!=plan['boot_id']:raise ValueError('Unexpected board reboot')
    after=protected_snapshot(client)
    allowed={PROD+'/'+name for name in plan['changed']}
    for path,value in plan['before']['hashes'].items():
        if path not in allowed and after['hashes'].get(path)!=value:
            raise ValueError('Protected model/PL/boot/service file changed: '+path)
    if audit_configs(client)!=plan['configs']:raise ValueError('Service/MI config changed')
    with client.open_sftp() as s:
        for name,value in plan['hashes'].items():
            if hashlib.sha256(s.open(PROD+'/'+name,'rb').read()).hexdigest()!=value:
                raise ValueError('Installed hash mismatch: '+name)
    dump(OUT/'VERIFICATION.json',dict(passed=True,probe=probe,after=after,pl_changed=False,
        models_changed=False,thresholds_changed=False,boot_changed=False,
        real_cued_trial_started=False,accuracy_claimed=False,normal_boot_retested=False))
    plan['phase']='verified';dump(OUT/'deployment.json',plan)
    print('FORMAL_ARM_UPDATE_VERIFIED',flush=True)


def main():
    global OUT, CHANGED, NEW, TESTS, RAW_RECORDING_PROFILE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('stage','check-stage','activate','verify','rollback'))
    parser.add_argument('--raw-recording',action='store_true',help='Update linked SSVEP raw recording instead of the original producer migration')
    args=parser.parse_args()
    if args.raw_recording:
        RAW_RECORDING_PROFILE=True
        OUT=ROOT/'eeg_apps_z15/output/ssvep_raw_sync_20261002'
        CHANGED=('cyton_trial_recorder.py','cyton_guardianloop.py','ssvep_cue_runtime.py',
                 'ssvep_cued.py','guardianloop_web.py')
        NEW=None
        TESTS=TESTS+('test_cyton_trial_recorder',)
    client=connect()
    try:
        if args.action=='stage':stage(client)
        elif args.action=='check-stage':complete_stage(client,ledger())
        elif args.action=='activate':activate(client)
        elif args.action=='verify':verify(client)
        else:rollback(client,ledger())
    finally:client.close()


if __name__=='__main__':main()

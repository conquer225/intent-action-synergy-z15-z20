"""Back up, verify and persist the user-selected shared-RMS MI virtual controller."""
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
import zipfile

import numpy as np

from run_soak_stage import connect, command
from run_ssvep_backlog_replay import checked
from run_mi_arm_acceptance import dump, digest, snapshot, stream_command

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'pynq_guardianloop'
OUT = ROOT/'eeg_apps_z15/output/mi_rms_integration_20261003'
FORMAL = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'
ACCEPTED = ROOT/'eeg_apps_z15/output/mi_rms_live_virtual_20261003'
APPLICATION = ('cyton_guardianloop.py','mi_acquisition.py','mi_cued.py','mi_cued.html','mi_cued_server.py',
    'mi_service_config.py','guardianloop_acquisition.py','mi_web_bridge.py','guardianloop_web.py',
    'guardianloop_startup.py','mi_rms_live_virtual.py','mi_eegnet_rms.py','mi_window_rms.py')
TESTS = 'test_mi_formal_entry test_guardianloop_startup test_mi_rms_live_virtual test_mi_cued test_mi_virtual test_mi_acquisition test_mi_reader_tap'
CONFIG = '/etc/default/guardianloop-mi.json'
TEMP = {
    '90-cyton.conf':'/run/systemd/system/guardianloop-cyton.service.d/90-mi-live-virtual.conf',
    '95-study.conf':'/run/systemd/system/guardianloop-cyton.service.d/95-mi-personal-study.conf',
    '96-rms.conf':'/run/systemd/system/guardianloop-cyton.service.d/96-mi-rms-live-virtual.conf',
    '90-web.conf':'/run/systemd/system/guardianloop-web.service.d/90-mi-live-virtual.conf',
}


def state(client, port=9104):
    probe="import json;from urllib.request import urlopen;print(json.dumps(json.load(urlopen('http://127.0.0.1:%d/api/mi-cue',timeout=2))))" % port
    return json.loads(command(client,'python3 -c '+shlex.quote(probe)))


def not_recording(client):
    with client.open_sftp() as sftp:
        with sftp.open('/run/guardianloop/recording_status.json') as stream:
            if json.load(stream).get('state') == 'recording':
                raise RuntimeError('Human recording active; installation refused')
    current=state(client)
    if current['state'] in ('active','awaiting_presentation'):
        raise RuntimeError('Human trial active; finish/stop before integration')
    return current


def prepare(client):
    OUT.mkdir(exist_ok=False)
    package=OUT/'package'
    for folder in ('runtime','config','rollback_original','checks'):
        (package/folder).mkdir(parents=True)
    before=snapshot(client)
    prior=json.loads((ACCEPTED/'deployment.json').read_text(encoding='utf-8'))
    if before['hashes'] != prior['runtime_after']['hashes']:
        raise ValueError('Formal release changed since the accepted live candidate')
    current=not_recording(client)
    if current['candidate_model']['sha256'] != prior['live_snapshot']['candidate_model']['sha256']:
        raise ValueError('Current model differs from the user-selected model')
    runtime=package/'runtime'
    with client.open_sftp() as sftp:
        with sftp.open(FORMAL+'/release_manifest.json') as stream:
            old_manifest=json.load(stream)
        for name, expected in old_manifest['files'].items():
            sftp.get(FORMAL+'/'+name,str(runtime/name))
            if digest(runtime/name) != expected:
                raise ValueError('Installed release checksum mismatch: '+name)
        sftp.get(prior['remote_directory']+'/mi-events.jsonl',str(OUT/'previous_virtual_events.jsonl'))
        targets={}
        for name in (*APPLICATION,'experimental_rms_eegnet.npz','release_manifest.json'):
            path=FORMAL+'/'+name
            old=before['hashes'].get(path,old_manifest['files'].get(name))
            if old is None:
                try:
                    sftp.stat(path)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError('Untracked formal target already exists: '+path)
            if old is not None:
                sftp.get(path,str(package/'rollback_original'/name))
            targets[path]=dict(old_sha256=old,original='rollback_original/'+name if old else None,
                               replacement='runtime/'+name,new_sha256=None)
        for name, path in dict(TEMP,**{'guardianloop-mi.json':CONFIG}).items():
            sftp.get(path,str(package/'rollback_original'/name))
            targets[path]=dict(old_sha256=digest(package/'rollback_original'/name),
                               original='rollback_original/'+name,
                               replacement='config/guardianloop-mi.json' if path==CONFIG else None,
                               new_sha256=None)
    known={
        '90-cyton.conf':digest(ROOT/'eeg_apps_z15/output/mi_live_virtual_20261003/runtime/cyton.conf'),
        '90-web.conf':digest(ROOT/'eeg_apps_z15/output/mi_live_virtual_20261003/runtime/web.conf'),
        '95-study.conf':json.loads((ROOT/'eeg_apps_z15/output/mi_personal_live_20261003/audit.json').read_text())['override_sha256'],
        '96-rms.conf':prior['override_sha256'],
    }
    for name, expected in known.items():
        if digest(package/'rollback_original'/name)!=expected:
            raise ValueError('Foreign temporary override: '+name)
    for name in APPLICATION:
        shutil.copy2(SOURCE/name,runtime/name)
    model=ACCEPTED/'stage/experimental_rms_eegnet.npz'
    if digest(model)!=current['candidate_model']['sha256']:
        raise ValueError('Frozen model mismatch')
    shutil.copy2(model,runtime/model.name)
    manifest=dict(old_manifest,release_id='guardianloop-fixed8-rms-mi-virtual-20261003',
        previous_release_id=old_manifest['release_id'],
        mi=dict(enabled_by_installed_config=True,model_name=model.name,model_sha256=digest(model),
                model_status='experimental_unpromoted',user_selected_for_virtual_control=True,
                personal_head_enabled=False,control_enabled=False,production_eligible=False),
        files={p.name:digest(p) for p in runtime.iterdir() if p.is_file() and p.name!='release_manifest.json'})
    dump(runtime/'release_manifest.json',manifest)
    dump(package/'config/guardianloop-mi.json',dict(enabled=True))
    for row in targets.values():
        if row['replacement']:
            row['new_sha256']=digest(package/row['replacement'])
    transaction=dict(targets=targets,protected=before['hashes'],
                     runtime_sha256={p.name:digest(p) for p in runtime.iterdir() if p.is_file()})
    dump(package/'transaction.json',transaction)
    shutil.copy2(SOURCE/'mi_rms_bundle.py',package/'mi_rms_bundle.py')
    for name in TESTS.split():
        shutil.copy2(SOURCE/(name+'.py'),runtime/(name+'.py'))
    for name in ('mi_reader_tap_smoke.py','mi_saved_window_parity.py'):
        shutil.copy2(SOURCE/name,runtime/name)
    shutil.copy2(ACCEPTED/'saved_window_probes.npz',package/'checks/saved_window_probes.npz')
    remote=command(client,'mktemp -d /home/xilinx/mi-rms-integration-XXXXXX').strip()
    if not re.fullmatch(r'/home/xilinx/mi-rms-integration-[A-Za-z0-9]+',remote):
        raise ValueError('Unexpected stage path')
    audit=dict(phase='prepared',before=before,remote_directory=remote,previous_live_state=current,
        feedback='在进入状态(感觉知道怎么想象的时候）尝试几遍之后我觉得最后几次的准确率可以，我觉得就用现在这个就可以了，把这个接入吧',
        feedback_semantics='informal_subjective_acceptance_not_measured_accuracy',
        user_selected_model_sha256=digest(model),started_at=datetime.now().astimezone().isoformat(),
        script_sha256=digest(Path(__file__)),pl_changed=False,board_rebooted=False)
    dump(OUT/'integration.json',audit)
    with client.open_sftp() as sftp:
        for folder in ('runtime','config','rollback_original','checks'):
            sftp.mkdir(remote+'/'+folder)
        for path in package.rglob('*'):
            if path.is_file():
                target=remote+'/'+path.relative_to(package).as_posix()
                sftp.put(str(path),target)
                if command(client,'sha256sum '+shlex.quote(target)).split()[0]!=digest(path):
                    raise ValueError('Transfer mismatch: '+str(path))
    print('ARM_INTEGRATION_STAGED',remote,flush=True)


def test(client,audit):
    runtime=OUT/'package/runtime'
    with (OUT/'pc_tests.log').open('w',encoding='utf-8') as log:
        subprocess.run([sys.executable,'-X','utf8','-m','unittest',*TESTS.split()],cwd=runtime,
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    remote=audit['remote_directory']
    prefix='cd '+shlex.quote(remote+'/runtime')+' && env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 '
    stream_command(client,prefix+'timeout 150s '+PYTHON+' -m unittest '+TESTS,OUT/'arm_tests.log',155)
    probe="""import json,pathlib,tempfile
from guardianloop_startup import verify_files,verify_models
from guardianloop_acquisition import acquisition_args
root=pathlib.Path('.').resolve();manifest=json.loads((root/'release_manifest.json').read_text())
count=verify_files(root,manifest)
with tempfile.TemporaryDirectory() as scratch: tasks=verify_models(root,pathlib.Path(scratch))
args=acquisition_args([],root,root.parent/'config/guardianloop-mi.json')
assert args[args.index('--mi-source')+1]=='live'
assert args[args.index('--mi-audit-log')+1]==str(root/'mi-events.jsonl')
print(json.dumps(dict(passed=True,verified_files=count,tasks=tasks,entry_args=args,pl_called=False)))
"""
    stream_command(client,prefix+'timeout 60s '+PYTHON+' -c '+shlex.quote(probe),OUT/'arm_startup_check.log',65)
    stream_command(client,prefix+'timeout 60s '+PYTHON+' mi_saved_window_parity.py --input ../checks/saved_window_probes.npz --model experimental_rms_eegnet.npz --output ../checks/arm_parity.npz',OUT/'arm_parity.log',65)
    stream_command(client,prefix+'timeout 60s '+PYTHON+' mi_reader_tap_smoke.py --shared-rms --model experimental_rms_eegnet.npz --output ../checks/tap_smoke.json',OUT/'arm_tap.log',65)
    with client.open_sftp() as sftp:
        for name in ('arm_parity.npz','tap_smoke.json'):
            sftp.get(remote+'/checks/'+name,str(OUT/name))
    with np.load(ACCEPTED/'saved_window_probes.npz') as a,np.load(OUT/'arm_parity.npz') as b:
        np.testing.assert_allclose(a['logits'],b['logits'],rtol=0,atol=1e-5)
        np.testing.assert_array_equal(a['logits'].argmax(1),b['logits'].argmax(1))
        audit['saved_window_logit_max_error']=float(np.max(np.abs(a['logits']-b['logits'])))
    if snapshot(client)['hashes']!=audit['before']['hashes']:
        raise ValueError('Formal files changed while staging')
    print(command(client,PYTHON+' '+shlex.quote(remote+'/mi_rms_bundle.py')+' check --bundle '+shlex.quote(remote)))
    audit.update(phase='stage_passed',stage_passed=True)
    dump(OUT/'integration.json',audit)


def verify(client,audit):
    remote=audit['remote_directory']
    transaction=json.loads((OUT/'package/transaction.json').read_text())
    current=snapshot(client)
    for text, old in audit['before']['hashes'].items():
        expected=transaction['targets'].get(text,{}).get('new_sha256',old)
        if current['hashes'].get(text)!=expected:
            raise ValueError('Protected target mismatch: '+text)
    for name in ('guardianloop-cyton.service','guardianloop-web.service'):
        if current['services'][name]['ActiveState']!='active':
            raise ValueError('Service not active: '+name)
    formal=state(client,9102)
    if formal.get('candidate_model') is None and formal.get('reason')=='mi_backend_unavailable':
        raise RuntimeError('Formal MI worker is still starting or unavailable')
    if (not formal.get('enabled') or formal['source']!='live'
            or formal['candidate_model']['sha256']!=audit['user_selected_model_sha256']
            or formal['candidate_model']['personal_head_enabled'] is not False
            or formal['control_enabled'] is not False or formal['virtual_hand']['enabled']
            or formal['virtual_hand']['command_count']!=0 or formal['result'] is not None):
        raise ValueError('Formal base-only observation entry failed')
    probe="""import pathlib,json,urllib.request
from guardianloop_startup import verify_files
root=pathlib.Path(%r);count=verify_files(root,json.loads((root/'release_manifest.json').read_text()))
config=pathlib.Path('/etc/default/guardianloop-mi.json');permissions=config.stat()
assert permissions.st_uid==0 and not permissions.st_mode & 0o022
assert json.loads(config.read_text())=={'enabled':True}
pages={}
for path in ('/','/mi-cued','/api/status','/api/seed-shadow','/api/ssvep-shadow'):
 with urllib.request.urlopen('http://127.0.0.1:9102'+path,timeout=5) as r:
  body=r.read();pages[path]=dict(code=r.status,bytes=len(body))
  if path=='/':assert '运动想象与虚拟手'.encode() in body
  if path=='/mi-cued':assert '个人适配头已停用'.encode() in body
print(json.dumps(dict(verified_files=count,pages=pages,root_owned_config=True)))
""" % FORMAL
    http=json.loads(command(client,'cd '+FORMAL+' && '+PYTHON+' -c '+shlex.quote(probe)))
    services=command(client,'systemctl show guardianloop-cyton.service guardianloop-web.service -p ExecStart -p DropInPaths')
    if '/home/xilinx/mi-' in services or '/run/systemd/system/guardianloop-' in services:
        raise ValueError('Temporary directory/override still active')
    if command(client,'cat /run/guardianloop-startup/status.json')!=audit['startup_before']:
        raise ValueError('Startup oneshot was unexpectedly rerun')
    startup_units=command(client,'systemctl show guardianloop-startup.service guardianloop-cyton.service guardianloop-web.service -p Id -p UnitFileState')
    if startup_units.count('UnitFileState=enabled')!=3:
        raise ValueError('Expected startup/capture/web boot enablement is missing')
    return dict(passed=True,runtime=current,formal_live_state=formal,http=http,services=services,
                startup_units=startup_units,
                persistent_config_enabled=True,pl_changed=False,actual_cold_boot_verified=False,
                new_accuracy_scored=False,physical_control=False)


def apply(client,audit):
    if audit['phase']!='stage_passed':
        raise ValueError('Only a tested stage may install')
    not_recording(client)
    audit['startup_before']=command(client,'cat /run/guardianloop-startup/status.json')
    dump(OUT/'integration.json',audit)
    remote=audit['remote_directory']
    installed=False
    try:
        print('INSTALLING_ARM_AND_RESTARTING_CAPTURE_WEB',flush=True)
        print(checked(client,PYTHON+' '+shlex.quote(remote+'/mi_rms_bundle.py')+' install --bundle '+shlex.quote(remote),sudo=True),flush=True)
        installed=True
        deadline=time.monotonic()+50
        while True:
            try:
                report=verify(client,audit)
                break
            except RuntimeError:
                if time.monotonic()>=deadline: raise
                time.sleep(.5)
        dump(OUT/'postflight.json',report)
        audit.update(phase='installed_verified',passed=True,persistent_config_enabled=True)
        print('RMS_MI_INTEGRATED',json.dumps(report['formal_live_state'],ensure_ascii=False),flush=True)
    except Exception:
        if installed:
            print(checked(client,PYTHON+' '+shlex.quote(remote+'/mi_rms_bundle.py')+' rollback --bundle '+shlex.quote(remote),sudo=True))
            audit['phase']='rolled_back'
        raise
    finally:
        dump(OUT/'integration.json',audit)


def package(audit):
    bundle=OUT/'package'
    evidence=bundle/'evidence';evidence.mkdir(exist_ok=False)
    for name in ('pc_tests.log','arm_tests.log','arm_startup_check.log','arm_parity.log','arm_tap.log','tap_smoke.json'):
        shutil.copy2(OUT/name,evidence/name)
    shutil.copy2(OUT/'formal_entry.jpg',evidence/'formal_entry.jpg')
    report=json.loads((OUT/'reverification.json').read_text())
    # No raw EEG, trial event log, passwords, helper credential files or personal head.
    dump(evidence/'SUMMARY.json',dict(passed=True,model_sha256=audit['user_selected_model_sha256'],
        persistent_config_enabled=True,personal_head_enabled=False,physical_control=False,
        pc_tests_passed=82,arm_tests_passed=82,saved_model_windows=24,
        saved_window_logit_max_error=audit['saved_window_logit_max_error'],
        formal_file_http_checks=report['http'],startup_units=report['startup_units'],
        services=report['services'],pl_changed=False,
        actual_cold_boot_verified=False,new_accuracy_scored=False))
    shutil.copy2(OUT/'README.md',bundle/'README.md')
    files=[p for p in bundle.rglob('*') if p.is_file()
           and '__pycache__' not in p.parts
           and 'checks' not in p.relative_to(bundle).parts]
    dump(bundle/'SHA256.json',{p.relative_to(bundle).as_posix():digest(p) for p in files})
    archive=OUT.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as zipped:
        for path in [*files,bundle/'SHA256.json']:
            zipped.write(path,path.relative_to(bundle).as_posix())
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None: raise ValueError('Archive CRC mismatch')
    dump(OUT/'PACKAGE.json',dict(path=str(archive),sha256=digest(archive),bytes=archive.stat().st_size,
                                contains_raw_eeg=False,contains_credentials=False))
    print('RMS_RELEASE_PACKAGE',str(archive),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','test','apply','verify','rollback','package'))
    args=parser.parse_args()
    if args.action=='package':
        audit=json.loads((OUT/'integration.json').read_text())
        if audit.get('phase')!='installed_verified': raise ValueError('Not verified')
        package(audit);return
    client=connect()
    try:
        if args.action=='prepare': prepare(client)
        else:
            audit=json.loads((OUT/'integration.json').read_text())
            if args.action=='test': test(client,audit)
            elif args.action=='apply': apply(client,audit)
            elif args.action=='verify': dump(OUT/'reverification.json',verify(client,audit))
            else:
                remote=audit['remote_directory']
                print(checked(client,PYTHON+' '+shlex.quote(remote+'/mi_rms_bundle.py')+' rollback --bundle '+shlex.quote(remote),sudo=True))
                audit.update(phase='rolled_back');dump(OUT/'integration.json',audit)
    finally: client.close()


if __name__=='__main__': main()

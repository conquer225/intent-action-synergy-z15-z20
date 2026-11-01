"""Stage, test and reversibly install the default-off MI ARM entry; never touch PL."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import time
from urllib.error import URLError

from run_soak_stage import ROOT, PROD, connect, command
from run_mi_arm_acceptance import PYTHON, digest, dump, stream_command
from run_mi_multitask import protected_snapshot
from deploy_ssvep_rail_coalesce import sudo

SOURCE = ROOT/'pynq_guardianloop'
ACCEPTED = ROOT/'eeg_apps_z15/output/mi_multitask_20261002_retry8'
OUT = ROOT/'eeg_apps_z15/output/mi_formal_entry_20261002'
MI_CORE = ('cyton_guardianloop.py','mi_acquisition.py','mi_cued.py','mi_cued_server.py',
           'mi_cued.html','mi_eegnet_portable.py','mi_features.py')
NEW = ('mi_service_config.py','guardianloop_acquisition.py','mi_web_bridge.py')
CONFIGS = {
    'guardianloop-mi.json':'/etc/default/guardianloop-mi.json',
    'guardianloop-cyton-mi.conf':'/etc/systemd/system/guardianloop-cyton.service.d/30-mi-entry.conf',
}
TESTS = ('test_mi_formal_entry','test_guardianloop_startup','test_seed_shadow_web','test_ssvep_cued',
         'test_cyton_reader_faults','test_small_batch','test_mi_acquisition','test_mi_cued',
         'test_mi_cued_replay','test_mi_eegnet_portable','test_mi_cued_acceptance')
REPLACED = ('cyton_guardianloop.py','guardianloop_web.py','release_manifest.json')


def stage(client):
    if (OUT/'deployment.json').exists():
        raise RuntimeError('Existing stage; inspect it rather than relaunch')
    verification=json.loads((ACCEPTED/'VERIFICATION.json').read_text())
    audit=json.loads((ACCEPTED/'audit.json').read_text())
    if not verification['passed']:
        raise ValueError('MI isolation did not pass')
    for name in MI_CORE:
        if digest(SOURCE/name)!=audit['source_sha256'][str(SOURCE/name)]:
            raise ValueError('Accepted MI source changed: '+name)
    before=protected_snapshot(client)
    if before['hashes']!=json.loads((OUT/'before.json').read_text())['hashes']:
        raise ValueError('Production changed since read-only audit')
    command(client,'systemctl is-active --quiet guardianloop-startup.service guardianloop-web.service')
    old=json.loads((OUT/'release_manifest.json').read_text())
    for name,value in old['files'].items():
        if before['hashes'][PROD+'/'+name]!=value:
            raise ValueError('Installed release mismatch: '+name)
    installed=OUT/'package/runtime';installed.mkdir(parents=True,exist_ok=False)
    original=OUT/'original';original.mkdir()
    location=command(client,'mktemp -d /home/xilinx/mi-formal-entry-XXXXXX').strip()
    if not location.startswith('/home/xilinx/mi-formal-entry-') or not Path(location).name.replace('-','').isalnum():
        raise ValueError('Unexpected private directory')
    ledger=dict(stage=location,started_pc_local=datetime.now().isoformat(),before=before,
                phase='staging',default_enabled=False,pl_changed=False,boot_changed=False)
    dump(OUT/'deployment.json',ledger)
    with client.open_sftp() as s:
        for path in CONFIGS.values():
            try:s.stat(path)
            except FileNotFoundError:pass
            else:raise ValueError('New configuration target already exists: '+path)
        for name in old['files']:
            s.get(PROD+'/'+name,str(installed/name))
        for name in REPLACED:
            s.get(PROD+'/'+name,str(original/name))
            s.put(str(original/name),location+'/'+name+'.original')
        for name in MI_CORE+NEW+('guardianloop_web.py',):
            if name not in REPLACED:
                try:s.stat(PROD+'/'+name)
                except FileNotFoundError:pass
                else:raise ValueError('New runtime target already exists: '+name)
            shutil.copy2(SOURCE/name,installed/name)
        model=ROOT/'eeg_apps_z15/output/mi_cued_delivery_20261002_final/experimental_eegnet.npz'
        if digest(model)!='178ad7c177adde6fdc939969a40bf25d9e0802d6b230b9127063f14c8402d7e6':
            raise ValueError('Experimental model changed')
        shutil.copy2(model,installed/model.name)
        manifest=dict(old,release_id='guardianloop-fixed-cap-mi-entry-20261002',
            previous_release_id=old['release_id'],mi=dict(default_enabled=False,
            model_status='experimental_unpromoted',production_eligible=False,control_enabled=False),
            files={p.name:digest(p) for p in sorted(installed.iterdir()) if p.is_file()})
        dump(installed/'release_manifest.json',manifest)
        for p in installed.iterdir():s.put(str(p),location+'/'+p.name)
        for name in CONFIGS:
            dest=OUT/'package/systemd'/name;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(SOURCE/name,dest);s.put(str(dest),location+'/'+name)
        for name in TESTS:
            s.put(str(SOURCE/(name+'.py')),location+'/'+name+'.py')
        for name in ('mi_cued_replay.py','mi_cued_acceptance.py'):
            s.put(str(SOURCE/name),location+'/'+name)
    ledger['manifest']=manifest
    ledger['application_hashes']=dict(manifest['files'],**{'release_manifest.json':digest(installed/'release_manifest.json')})
    ledger['install_hashes']={name:ledger['application_hashes'][name]
        for name in MI_CORE+NEW+('guardianloop_web.py','experimental_eegnet.npz','release_manifest.json')}
    ledger['config_hashes']={name:digest(SOURCE/name) for name in CONFIGS}
    dump(OUT/'deployment.json',ledger)
    invoke='cd '+shlex.quote(location)+' && env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr '+PYTHON
    stream_command(client,invoke+' -m unittest '+' '.join(TESTS),OUT/'arm-tests.log',90)
    check_stage(client,ledger)


def check_stage(client,ledger):
    if ledger['phase']!='staging' or not (OUT/'arm-tests.log').read_text().rstrip().endswith('OK'):
        raise ValueError('Stage tests have not completed successfully')
    with client.open_sftp() as s:
        for name,value in dict(ledger['application_hashes'],**ledger['config_hashes']).items():
            if hashlib.sha256(s.open(ledger['stage']+'/'+name,'rb').read()).hexdigest()!=value:
                raise ValueError('Staged file changed: '+name)
    invoke='cd '+shlex.quote(ledger['stage'])+' && env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 XILINX_XRT=/usr '+PYTHON
    probe="""import json,pathlib,tempfile
from guardianloop_startup import verify_files,verify_models
root=pathlib.Path('.')
manifest=json.loads((root/'release_manifest.json').read_text())
count=verify_files(root,manifest)
with tempfile.TemporaryDirectory() as scratch:
 tasks=verify_models(root,pathlib.Path(scratch))
print(json.dumps(dict(passed=True,verified_files=count,tasks=tasks,pl_called=False)))
"""
    _,stdout,stderr=client.exec_command(invoke+' -c '+shlex.quote(probe),timeout=30)
    raw=stdout.read().decode()
    warnings=stderr.read().decode()
    (OUT/'stage-arm-check.stdout').write_text(raw,encoding='utf-8')
    (OUT/'stage-arm-check.stderr').write_text(warnings,encoding='utf-8')
    if stdout.channel.recv_exit_status():raise RuntimeError(warnings)
    value=json.loads(raw)
    dump(OUT/'stage-arm-check.json',value)
    after=protected_snapshot(client)
    if after['hashes']!=ledger['before']['hashes']:
        raise ValueError('Production changed during stage')
    ledger.update(phase='stage_passed',stage_passed=True)
    dump(OUT/'deployment.json',ledger)
    print('MI_FORMAL_STAGE_PASSED',ledger['stage'],flush=True)


def postflight(client,ledger):
    with client.open_sftp() as s:
        for name,value in ledger['application_hashes'].items():
            if hashlib.sha256(s.open(PROD+'/'+name,'rb').read()).hexdigest()!=value:
                raise ValueError('Installed application mismatch: '+name)
        for name,path in CONFIGS.items():
            if hashlib.sha256(s.open(path,'rb').read()).hexdigest()!=ledger['config_hashes'][name]:
                raise ValueError('Installed configuration mismatch: '+name)
    probe="""import json,pathlib,urllib.request
root=pathlib.Path(%r)
import sys
sys.path.insert(0,str(root))
from guardianloop_startup import verify_files
manifest=json.loads((root/'release_manifest.json').read_text())
count=verify_files(root,manifest)
urls=('/','/mi-cued','/api/mi-cue','/api/status','/api/ssvep-cue','/api/seed-shadow','/api/ssvep-shadow')
http={}
for path in urls:
 with urllib.request.urlopen('http://127.0.0.1:9102'+path,timeout=5) as r:
  body=r.read();http[path]=json.loads(body) if path.startswith('/api/') else dict(status=r.status,bytes=len(body),mi_entry=b'/mi-cued' in body,disabled='默认关闭'.encode() in body)
listeners=[]
for name in ('tcp','tcp6'):
 for line in pathlib.Path('/proc/net/'+name).read_text().splitlines()[1:]:
  cols=line.split()
  if cols[3]=='0A' and int(cols[1].split(':')[1],16)==9104:listeners.append(cols[1])
processes=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:cmd=(p/'cmdline').read_bytes().replace(b'\\0',b' ').decode()
 except (OSError,UnicodeError):continue
 if str(root)+'/guardianloop_acquisition.py' in cmd and not ' -c ' in cmd:processes.append(dict(pid=int(p.name),command=cmd))
print(json.dumps(dict(verified_files=count,http=http,mi_listeners=listeners,acquisition_processes=processes)))
"""%PROD
    value=json.loads(command(client,PYTHON+' -c '+shlex.quote(probe)))
    assert value['http']['/']['mi_entry'] and value['http']['/mi-cued']['disabled']
    mi=value['http']['/api/mi-cue']
    assert mi['state']=='disabled' and mi['enabled'] is False and mi['result'] is None
    assert mi['control_enabled'] is False and mi['production_eligible'] is False
    assert not value['mi_listeners']
    snapshot=protected_snapshot(client)
    allowed={PROD+'/'+name for name in REPLACED}
    for path,sha in ledger['before']['hashes'].items():
        if path not in allowed and snapshot['hashes'].get(path)!=sha:
            raise ValueError('Protected file changed: '+path)
    command(client,'systemctl is-active --quiet guardianloop-startup.service guardianloop-web.service')
    drop=command(client,'systemctl show guardianloop-cyton.service -p ExecStart -p After -p Requires')
    assert 'guardianloop_acquisition.py' in drop and 'guardianloop-startup.service' in drop
    return dict(passed=True,checks=value,snapshot=snapshot,service_entry=drop,pl_changed=False,
                live_cyton_verified=False,accuracy_verified=False,mi_enabled=False)


def rollback(client,ledger):
    location=ledger['stage']
    # Never overwrite someone else's post-deployment changes.
    with client.open_sftp() as s:
        for name,sha in ledger['install_hashes'].items():
            try:actual=hashlib.sha256(s.open(PROD+'/'+name,'rb').read()).hexdigest()
            except FileNotFoundError:continue
            old=ledger['before']['hashes'].get(PROD+'/'+name)
            if actual not in (sha,old):raise ValueError('Rollback refused foreign change: '+name)
        for name,path in CONFIGS.items():
            try:actual=hashlib.sha256(s.open(path,'rb').read()).hexdigest()
            except FileNotFoundError:continue
            if actual!=ledger['config_hashes'][name]:raise ValueError('Rollback refused foreign config: '+path)
    sudo(client,'systemctl stop guardianloop-cyton.service guardianloop-web.service')
    for name in REPLACED:
        sudo(client,'install -m 644 '+shlex.quote(location+'/'+name+'.original')+' '+shlex.quote(PROD+'/'+name))
    for name in ledger['install_hashes']:
        if name in REPLACED:continue
        sudo(client,'if test -f '+shlex.quote(PROD+'/'+name)+'; then mv '+shlex.quote(PROD+'/'+name)+' '+shlex.quote(location+'/'+name+'.withdrawn')+'; fi')
    for name,path in CONFIGS.items():
        sudo(client,'if test -f '+shlex.quote(path)+'; then mv '+shlex.quote(path)+' '+shlex.quote(location+'/'+name+'.withdrawn')+'; fi')
    sudo(client,'systemctl daemon-reload')
    sudo(client,'systemctl start guardianloop-web.service guardianloop-cyton.service')
    current=protected_snapshot(client)
    assert current['hashes']==ledger['before']['hashes']
    ledger.update(phase='rolled_back')
    dump(OUT/'deployment.json',ledger)


def apply(client):
    ledger=json.loads((OUT/'deployment.json').read_text())
    if ledger['phase']!='stage_passed':raise ValueError('Only a passed, uninstalled stage may apply')
    if protected_snapshot(client)['hashes']!=ledger['before']['hashes']:
        raise ValueError('Production changed; refused install')
    if command(client,'cat /run/guardianloop-startup/status.json')!= (OUT/'startup.json').read_text():
        raise ValueError('Startup state changed; refused install')
    location=ledger['stage']
    ledger.update(phase='applying');dump(OUT/'deployment.json',ledger)
    try:
        sudo(client,'systemctl stop guardianloop-cyton.service guardianloop-web.service')
        for name in ledger['install_hashes']:
            sudo(client,'install -m 644 '+shlex.quote(location+'/'+name)+' '+shlex.quote(PROD+'/'+name))
        for name,path in CONFIGS.items():
            sudo(client,'install -m 644 '+shlex.quote(location+'/'+name)+' '+shlex.quote(path))
        sudo(client,'systemctl daemon-reload')
        # Startup is already active; do not restart its PL-loading oneshot.
        command(client,'systemctl is-active --quiet guardianloop-startup.service')
        sudo(client,'systemctl start guardianloop-web.service guardianloop-cyton.service')
        for attempt in range(10):
            try:
                result=postflight(client,ledger)
                break
            except (OSError, URLError, RuntimeError):
                if attempt==9:raise
                time.sleep(1)
        assert command(client,'cat /run/guardianloop-startup/status.json')==(OUT/'startup.json').read_text()
        dump(OUT/'postflight.json',result)
        ledger.update(phase='installed_verified',passed=True)
        dump(OUT/'deployment.json',ledger)
        print('MI_FORMAL_INSTALLED_DEFAULT_OFF',flush=True)
    except Exception:
        rollback(client,ledger)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('stage','complete-stage','apply','rollback','verify'))
    action=parser.parse_args().action
    client=connect()
    try:
        if action=='stage':stage(client)
        elif action=='apply':apply(client)
        else:
            ledger=json.loads((OUT/'deployment.json').read_text())
            if action=='rollback':rollback(client,ledger)
            elif action=='complete-stage':check_stage(client,ledger)
            else:dump(OUT/'reverification.json',postflight(client,ledger))
    finally:client.close()


if __name__=='__main__':main()

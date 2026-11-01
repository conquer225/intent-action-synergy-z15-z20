"""Prepare the exact software package; install only after the replay check passes."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex

import run_live_system as helpers

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'phone_video_upload/output/load_relief_20261007'
SOURCE=OUT/'candidate_source'
STATE=OUT/'deployment-state.json'
FORMAL='/home/xilinx/jupyter_notebooks/guardianloop_pynq'
MEDIA='/home/xilinx/gl-media-20261007-314e8796'
EYE='/home/xilinx/brain_eye_coexist_20261005/eye/src/coexist_guard.py'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(client):
    if STATE.exists():raise ValueError('Existing deployment must be inspected')
    gate=json.loads((OUT/'scheduled/array_scheduled-checks.json').read_text())
    if not gate['promotion_gate']:raise ValueError('Candidate gate failed')
    previous=OUT/'formal_source/release_manifest.json'
    if helpers.execute(client,'sha256sum '+FORMAL+'/release_manifest.json').split()[0]!=sha(previous):
        raise ValueError('Pinned formal manifest changed')
    incoming={
        'cyton_guardianloop.py':SOURCE/'cyton_guardianloop.py',
        'cyton_covariance.py':ROOT/'pynq_guardianloop/cyton_covariance.py',
        'ssvep_acquisition.py':ROOT/'pynq_guardianloop/ssvep_acquisition.py',
        'async_seed_candidate.py':ROOT/'pynq_guardianloop/async_seed_candidate.py',
        'page_policy.py':ROOT/'guardianloop_system/page_policy.py',
    }
    manifest=json.loads(previous.read_text())
    manifest['previous_release_id']=manifest['release_id']
    manifest['release_id']='guardianloop-fixed8-load-relief-20261007'
    manifest['files'].update({name:sha(path) for name,path in incoming.items()})
    manifest['load_relief']=dict(primary_models_changed=False,pl_changed=False,
        covariance_storage='array',seed_candidate='bounded_async_paused_optional_diagnostic',
        ssvep_schedule='HDMI_direction_page_or_standalone',
        primary_numeric_parity_windows=gate['common_windows'],
        live_HDMI_acceptance=False,scope=gate['scope'])
    path=SOURCE/'release_manifest.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    incoming['release_manifest.json']=path
    targets=[(FORMAL+'/'+name,path) for name,path in incoming.items()]
    targets += [(MEDIA+'/'+name,ROOT/'phone_video_upload'/name) for name in ('system_hdmi.py','media_player.py')]
    targets += [(MEDIA+'/menu-shells-portrait-live.npz',OUT/'menu_assets/menu-shells-portrait-live.npz'),
                (MEDIA+'/system_runtime/guardianloop_system/page_policy.py',ROOT/'guardianloop_system/page_policy.py'),
                ('/etc/systemd/system/guardianloop-cyton.service.d/50-load-relief.conf',SOURCE/'50-load-relief.conf')]
    stage=helpers.execute(client,'mktemp -d /home/xilinx/gl-load-relief-install-XXXXXX').strip()
    helpers.execute(client,'mkdir '+stage+'/payload')
    plan=dict(previous_manifest_sha=sha(previous),gate={key:gate[key] for key in
        ('promotion_gate','primary_numeric_parity','complete_no_error','latency_improved','common_windows')},files=[])
    with client.open_sftp() as ftp:
        ftp.get(EYE,str(SOURCE/'coexist_guard.py'))
        ftp.put(str(ROOT/'pynq_guardianloop/install_load_relief.py'),stage+'/install_load_relief.py')
        for index,(target,source) in enumerate(targets):
            key='file-'+str(index)+source.suffix
            try:
                with ftp.open(target,'rb') as handle:old=hashlib.sha256(handle.read()).hexdigest()
            except FileNotFoundError:old=None
            ftp.put(str(source),stage+'/payload/'+key)
            if helpers.execute(client,'sha256sum '+stage+'/payload/'+key).split()[0]!=sha(source):
                raise ValueError('Package transfer differs')
            plan['files'].append(dict(key=key,target=target,new_sha=sha(source),old_sha=old))
        ftp.get(EYE,str(OUT/'formal_source/coexist_guard.py'))
    (OUT/'deployment-plan.json').write_text(json.dumps(plan,indent=2))
    STATE.write_text(json.dumps(dict(stage=stage,manifest_sha=sha(path)),indent=2))
    print(json.dumps(dict(stage=stage,new_manifest_sha=sha(path),next='Update the one pinned coexist guard hash, then install')))


def install(client):
    state=json.loads(STATE.read_text());stage=state['stage']
    guard=SOURCE/'coexist_guard.py'
    if ("EXPECTED_MANIFEST = '"+state['manifest_sha']+"'") not in guard.read_text():
        raise ValueError('Coexist guard does not pin this exact software package')
    plan=json.loads((OUT/'deployment-plan.json').read_text())
    original=OUT/'formal_source/coexist_guard.py'
    plan['files'].append(dict(key='coexist_guard.py',target=EYE,new_sha=sha(guard),old_sha=sha(original)))
    (OUT/'deployment-plan.json').write_text(json.dumps(plan,indent=2))
    with client.open_sftp() as ftp:
        ftp.put(str(guard),stage+'/payload/coexist_guard.py')
        ftp.put(str(OUT/'deployment-plan.json'),stage+'/deployment-plan.json')
    print(helpers.execute(client,shlex.join(['systemd-run','--unit='+stage.rsplit('/',1)[1],
        '--property=RuntimeMaxSec=90s','--property=TimeoutStopSec=5s','--property=KillMode=control-group',
        'env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',helpers.PYTHON,
        stage+'/install_load_relief.py','install']),True))


def collect(client):
    state=json.loads(STATE.read_text());stage=state['stage'];archive=stage+'/software-recovery.tar.gz'
    commands=['set -e',shlex.join(['tar','-czf',archive,'-C',stage,'backup','install_load_relief.py','deployment-plan.json']),
              shlex.join(['chown','xilinx:xilinx',archive]),shlex.join(['chmod','600',archive])]
    helpers.execute(client,'bash -c '+shlex.quote('\n'.join(commands)),True)
    with client.open_sftp() as ftp:
        ftp.get(archive,str(OUT/'software-recovery.tar.gz'))
        ftp.get(stage+'/verification.json',str(OUT/'installation-verification.json'))
    expected=helpers.execute(client,'sha256sum '+archive).split()[0]
    if sha(OUT/'software-recovery.tar.gz')!=expected:raise ValueError('Rollback archive transfer differs')
    (OUT/'software-recovery.tar.gz.sha256').write_text(expected+'\n')
    log=helpers.execute(client,'journalctl -u '+stage.rsplit('/',1)[1]+'-tests -o cat --no-pager',True)
    (OUT/'board-tests.log').write_text(log)
    code=r'''
import json,pathlib,urllib.request
d=json.loads(urllib.request.urlopen('http://127.0.0.1:9102/api/status',timeout=5).read())
f=d.get('fatigue',{});s=json.loads(pathlib.Path('/run/guardianloop/status.json').read_text())
print(json.dumps(dict(stale=d.get('stale'),fatigue={k:f.get(k) for k in
 ('valid','state','reason','packets_seen','calibration_current')},primary={k:s.get(k) for k in
 ('valid','state','reason','packets_seen')},no_old_prediction_retained=f.get('valid') is False)))
'''
    value=json.loads(helpers.execute(client,shlex.join([helpers.PYTHON,'-c',code])))
    (OUT/'final-live-status.json').write_text(json.dumps(value,indent=2))
    print(json.dumps(dict(live=value,recovery_sha256=expected)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','install','collect'))
    args=parser.parse_args();client=helpers.upload.trial.connect('192.168.2.99')
    try:globals()[args.action](client)
    finally:client.close()

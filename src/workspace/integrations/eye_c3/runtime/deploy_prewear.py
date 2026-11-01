"""Install the tested hardening using the existing checksummed rollback engine."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import stat

from stage_prewear import OUT, ROOT, STATE, LIVE, FORMAL, FORMAL_SOURCES, MEDIA_SOURCES
import run_hdmi_live as live

INSTALL=OUT/'installation-stage.json'
EYE='/home/xilinx/brain_eye_coexist_20261005/eye/src/coexist_guard.py'
STARTUP='/run/guardianloop-startup/status.json'
OVERRIDE='/run/systemd/system/guardianloop-cyton.service.d/90-guardianloop-hdmi-test.conf'
BOOT_UNIT='guardianloop-hdmi-entry.service'


def stage(client):
    if INSTALL.exists():raise ValueError('Installation stage exists; inspect it')
    tested=json.loads(STATE.read_text())
    if json.loads((OUT/'linux-tests.json').read_text())['exit_code']!=0:raise ValueError('Tests failed')
    for folder,names,prefix in (('pynq_guardianloop',FORMAL_SOURCES,'runtime/'),
                                ('phone_video_upload',MEDIA_SOURCES,'runtime/'),
                                ('guardianloop_system',('core.py','live_inputs.py'),'runtime/system_runtime/guardianloop_system/')):
        for n in names:
            if hashlib.sha256((ROOT/folder/n).read_bytes()).hexdigest()!=tested['hashes'][prefix+n]:
                raise ValueError('Source changed after Linux tests: '+n)
    current=json.loads(LIVE.read_text());base=current['remote'];runtime=current['candidate_runtime']
    remote=live.board.execute(client,'mktemp -d /home/xilinx/gl-calibration-install-20261008-XXXXXX').strip()
    payload=OUT/'payload';payload.mkdir(exist_ok=True)
    plan=dict(live=base,tests_passed=True,prewear_update=True,candidate_runtime=runtime,
              boot=current['boot'],files=[],web_services=['guardianloop-web.service',Path(base).name+'-server.service'])
    sha=lambda b:hashlib.sha256(b).hexdigest()
    with client.open_sftp() as ftp:
        def read(path):
            import base64
            return base64.b64decode(live.board.execute(client,shlex.join(['base64','-w0',path]),True))
        original=read(FORMAL+'/release_manifest.json');manifest=json.loads(original)
        if manifest['files']!=current['formal_hashes']:raise ValueError('Formal release changed')
        plan['previous_manifest_sha']=sha(original)
        def add(target,data,mode=0o644):
            try:
                info=ftp.lstat(target)
                if stat.S_ISLNK(info.st_mode):raise ValueError('Linked update target')
                old_sha,old_mode=sha(read(target)),stat.S_IMODE(info.st_mode)
            except FileNotFoundError:old_sha,old_mode=None,None
            key='%02d-%s'%(len(plan['files']),Path(target).name)
            (payload/key).write_bytes(data)
            plan['files'].append(dict(target=target,key=key,old_sha=old_sha,old_mode=old_mode,new_sha=sha(data),new_mode=mode))
        for n in FORMAL_SOURCES:
            data=(ROOT/'pynq_guardianloop'/n).read_bytes();add(FORMAL+'/'+n,data);manifest['files'][n]=sha(data)
        manifest['release_id']='guardianloop-fixed8-prewear-hardening-20261008'
        encoded=json.dumps(manifest,indent=2).encode();add(FORMAL+'/release_manifest.json',encoded)
        guard=read(EYE).decode();guard,count=re.subn(r"EXPECTED_MANIFEST = '[a-f0-9]{64}'","EXPECTED_MANIFEST = '"+sha(encoded)+"'",guard)
        if count!=1:raise ValueError('Unexpected release guard')
        add(EYE,guard.encode())
        startup=json.loads(read(STARTUP))
        if startup['state']!='ready' or startup['boot_id']!=current['boot']:raise ValueError('Startup differs')
        startup.update(release_id=manifest['release_id'],verified_files=len(manifest['files']),software_update_without_pl_reload=True)
        add(STARTUP,json.dumps(startup,indent=2).encode(),0o600)
        disk=json.loads(read(base+'/state.json'))
        if disk!=current or read(OVERRIDE).decode()!=current['override_text']:raise ValueError('Session owner changed')
        disk['formal_hashes']=manifest['files']
        for n in ('ssvep_hdmi.py','ssvep_cue_runtime.py'):
            data=(ROOT/'pynq_guardianloop'/n).read_bytes();add(runtime+'/'+n,data)
            disk['module_hashes'][Path(n).stem]=sha(data)
        add(base+'/state.json',json.dumps(disk,indent=2).encode(),0o600)
        media=json.loads(read(base+'/media_state.json'));media['boot']=disk['boot']
        add(base+'/media_state.json',json.dumps(media,indent=2).encode(),0o600)
        for n in MEDIA_SOURCES:add(base+'/'+n,(ROOT/'phone_video_upload'/n).read_bytes())
        for n in ('core.py','live_inputs.py'):
            add(base+'/system_runtime/guardianloop_system/'+n,(ROOT/'guardianloop_system'/n).read_bytes())
        unit=('[Unit]\nDescription=GuardianLoop private software entry (no automatic HDMI or flicker)\n'
              'After=network.target guardianloop-cyton.service guardianloop-web.service\n'
              'Wants=guardianloop-cyton.service guardianloop-web.service\n'
              '[Service]\nType=oneshot\nRemainAfterExit=yes\nTimeoutStartSec=180\nUMask=0077\n'
              'Environment=XILINX_XRT=/usr\nEnvironment=OPENBLAS_NUM_THREADS=1\n'
              'ExecStart='+live.board.PYTHON+' '+base+'/hdmi_boot.py\n'
              '[Install]\nWantedBy=multi-user.target\n')
        unit_path='/etc/systemd/system/'+BOOT_UNIT
        try:ftp.lstat(unit_path)
        except FileNotFoundError:pass
        else:raise ValueError('A persistent entry already exists; do not replace it')
        add(unit_path,unit.encode())
        pins=dict(manifest_sha256=sha(encoded),files={FORMAL+'/'+n:h for n,h in manifest['files'].items()})
        pins['files'][FORMAL+'/release_manifest.json']=sha(encoded)
        for row in plan['files']:
            if row['target'].startswith(base+'/') and Path(row['target']).name not in ('state.json','media_state.json'):
                pins['files'][row['target']]=row['new_sha']
            if row['target'].startswith(runtime+'/'):pins['files'][row['target']]=row['new_sha']
        for n,h in current['module_hashes'].items():pins['files'].setdefault(runtime+'/'+n+'.py',h)
        for p,h in media['hardware_hashes'].items():pins['files'][p]=h
        pins['files'][media['native_scan_library']]=media['native_scan_sha256']
        add(base+'/boot-pins.json',json.dumps(pins,indent=2).encode(),0o600)
        player=json.loads(read(base+'/player_status.json'));ident=player['session_id']
        if not re.fullmatch('play-[a-f0-9]{8}',ident):raise ValueError('Unexpected display owner')
        plan['display_unit']=ident+'.service'
        ftp.mkdir(remote+'/payload',mode=0o700)
        for row in plan['files']:ftp.put(str(payload/row['key']),remote+'/payload/'+row['key'])
        planfile=OUT/'deployment-plan.json';planfile.write_text(json.dumps(plan,indent=2))
        ftp.put(str(planfile),remote+'/deployment-plan.json');ftp.chmod(remote+'/deployment-plan.json',0o600)
        ftp.put(str(ROOT/'pynq_guardianloop/install_calibration_repair.py'),remote+'/install_calibration_repair.py')
    INSTALL.write_text(json.dumps(dict(remote=remote,live=base,display_unit=plan['display_unit']),indent=2))
    print('RECOVERABLE_PREWEAR_INSTALL_STAGED',len(plan['files']))


def operate(client,action):
    state=json.loads(INSTALL.read_text())
    print(live.board.execute(client,shlex.join(['env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',
        live.board.PYTHON,state['remote']+'/install_calibration_repair.py',action]),True))
    if action in ('install','commit','rollback'):
        disk=json.loads(live.board.execute(client,shlex.join(['cat',state['live']+'/state.json']),True))
        LIVE.write_text(json.dumps(disk,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('stage','install','commit','rollback'))
    args=parser.parse_args();client=live.board.upload.trial.connect('192.168.2.99')
    try:stage(client) if args.action=='stage' else operate(client,args.action)
    finally:client.close()

"""Prepare a recoverable production update, then install only after fault tests."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import stat

import run_hdmi_live as live
from stage_calibration_repair import OUT, ROOT, SOURCES, STATE as TEST_STATE

LIVE_STATE = ROOT/'phone_video_upload/output/hdmi_live_user_controlled_20261008/state.json'
INSTALL_STATE = OUT/'installation-stage.json'
FORMAL = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
MEDIA = '/home/xilinx/gl-media-20261007-314e8796'
EYE = '/home/xilinx/brain_eye_coexist_20261005/eye/src/coexist_guard.py'
STARTUP = '/run/guardianloop-startup/status.json'
OVERRIDE = '/run/systemd/system/guardianloop-cyton.service.d/90-guardianloop-hdmi-test.conf'


def digest(data):return hashlib.sha256(data).hexdigest()


def stage(client):
    if INSTALL_STATE.exists():raise ValueError('Installation stage already exists; inspect it')
    tested=json.loads(TEST_STATE.read_text());result=json.loads((OUT/'linux-tests.json').read_text())
    if result['exit_code']!=0:raise ValueError('Linux fault tests have not passed')
    for name in SOURCES:
        if digest((ROOT/'pynq_guardianloop'/name).read_bytes())!=tested['hashes'][name]:
            raise ValueError('Source changed after Linux tests')
    current=json.loads(LIVE_STATE.read_text());base=current['remote']
    remote=live.board.execute(client,'mktemp -d /home/xilinx/gl-calibration-install-20261008-XXXXXX').strip()
    payload=OUT/'payload';payload.mkdir(exist_ok=True)
    plan=dict(live=base,tests_passed=True,boot=current['boot'],files=[],
              web_services=['guardianloop-web.service',Path(base).name+'-server.service'])
    with client.open_sftp() as ftp:
        def read(path):
            try:
                with ftp.open(path,'rb') as stream:return stream.read()
            except PermissionError:
                import base64
                return base64.b64decode(live.board.execute(client,shlex.join(['base64','-w0',path]),True))
        original=read(FORMAL+'/release_manifest.json');manifest=json.loads(original)
        plan['previous_manifest_sha']=digest(original)
        if manifest['files']!=current['formal_hashes']:raise ValueError('Live session release changed')
        def add(target,data,mode=0o644):
            try:
                info=ftp.lstat(target);old=read(target)
                if stat.S_ISLNK(info.st_mode):raise ValueError('Linked update target')
                old_sha,old_mode=digest(old),stat.S_IMODE(info.st_mode)
            except FileNotFoundError:old_sha,old_mode=None,None
            key='%02d-%s'%(len(plan['files']),Path(target).name)
            (payload/key).write_bytes(data)
            plan['files'].append(dict(target=target,key=key,old_sha=old_sha,new_sha=digest(data),old_mode=old_mode,new_mode=mode))
        for name in (*SOURCES,'guardianloop_web.py','mobile.js'):
            data=(ROOT/'pynq_guardianloop'/name).read_bytes();add(FORMAL+'/'+name,data)
            manifest['files'][name]=digest(data)
        manifest['release_id']='guardianloop-fixed8-calibration-recovery-20261008'
        encoded=json.dumps(manifest,indent=2).encode();add(FORMAL+'/release_manifest.json',encoded)
        guard=read(EYE).decode()
        guard,n=re.subn(r"EXPECTED_MANIFEST = '[a-f0-9]{64}'", "EXPECTED_MANIFEST = '"+digest(encoded)+"'",guard)
        if n!=1:raise ValueError('Unexpected release guard')
        add(EYE,guard.encode())
        startup=json.loads(read(STARTUP))
        if startup['state']!='ready' or startup['boot_id']!=current['boot']:raise ValueError('Startup contract changed')
        startup.update(release_id=manifest['release_id'],verified_files=len(manifest['files']),
            software_update_without_pl_reload=True,calibration_recovery='same_boot_and_same_models_only')
        add(STARTUP,json.dumps(startup,indent=2).encode(),0o600)
        disk=json.loads(read(base+'/state.json'))
        if disk!=current:raise ValueError('Live-session state differs from local record')
        if read(OVERRIDE).decode()!=disk['override_text']:raise ValueError('Override owner differs')
        disk['formal_hashes']=manifest['files']
        disk['override_text']+='Environment=OPENBLAS_NUM_THREADS=1\nEnvironment=OMP_NUM_THREADS=1\n'
        add(base+'/state.json',json.dumps(disk,indent=2).encode(),0o600)
        add(OVERRIDE,disk['override_text'].encode(),0o600)
        ui=(('system_mobile.js','phone_video_upload/system_mobile.js'),
            ('system_hdmi.py','phone_video_upload/system_hdmi.py'),
            ('system_runtime/guardianloop_system/live_inputs.py','guardianloop_system/live_inputs.py'))
        for relative,local in ui:
            data=(ROOT/local).read_bytes();add(base+'/'+relative,data)
            # Preserve the older media entry's own SSVEP backend and HTML contract.
            older=read(MEDIA+'/'+relative).decode()
            if relative=='system_mobile.js':
                new=next(line for line in data.decode().splitlines() if line.startswith(" $('brain').textContent="))
                older,n=re.subn(r"^ \$\('brain'\)\.textContent=.*$",lambda _:new,older,flags=re.M)
                if n!=1:raise ValueError('Older mobile summary differs')
            elif relative=='system_hdmi.py':
                anchor="        key=(state.page,state.speed_level,state.direction,state.rating,state.video_index,mood,level,"
                if older.count(anchor)!=1:raise ValueError('Older HDMI summary differs')
                insert="        if fatigue.get('calibration_retained') is True and fatigue.get('valid') is not True:\n            mood='等待新鲜数据';level='校准已保留'\n"
                older=older.replace(anchor,insert+anchor)
            else:
                anchor="        return dict(connected=fresh,state='live' if ready else 'no_data',"
                if older.count(anchor)!=1:raise ValueError('Older brain adapter differs')
                insert="        unavailable={'valid':False,'level':'unknown','state':'no_data'}\n        if fresh and fatigue.get('calibration_retained') is True:\n            unavailable.update(calibration_retained=True,\n                calibration_current=fatigue.get('calibration_current',0),\n                calibration_total=fatigue.get('calibration_total',15))\n"
                older=older.replace(anchor,insert+anchor).replace("fatigue=fatigue if ready else {'valid':False,'level':'unknown','state':'no_data'},","fatigue=fatigue if ready else unavailable,")
            add(MEDIA+'/'+relative,older.encode())
        player=json.loads(read(base+'/player_status.json'))
        if not re.fullmatch('play-[a-f0-9]{8}',player['session_id']):raise ValueError('Unexpected display owner')
        plan['display_unit']=player['session_id']+'.service'
        ftp.mkdir(remote+'/payload',mode=0o700)
        for row in plan['files']:
            ftp.put(str(payload/row['key']),remote+'/payload/'+row['key'])
        planfile=OUT/'deployment-plan.json';planfile.write_text(json.dumps(plan,indent=2))
        ftp.put(str(planfile),remote+'/deployment-plan.json');ftp.chmod(remote+'/deployment-plan.json',0o600)
        ftp.put(str(ROOT/'pynq_guardianloop/install_calibration_repair.py'),remote+'/install_calibration_repair.py')
    record=dict(remote=remote,live=base,display_unit=plan['display_unit'])
    INSTALL_STATE.write_text(json.dumps(record,indent=2))
    print('PINNED_SOFTWARE_INSTALLATION_STAGED',len(plan['files']))


def run(client,action):
    s=json.loads(INSTALL_STATE.read_text())
    print(live.board.execute(client,shlex.join(['env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',
        live.board.PYTHON,s['remote']+'/install_calibration_repair.py',action]),True))
    if action in ('commit','rollback'):
        state=json.loads(live.board.execute(client,shlex.join(['cat',s['live']+'/state.json']),True))
        LIVE_STATE.write_text(json.dumps(state,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('stage','install','commit','rollback'))
    args=parser.parse_args();client=live.board.upload.trial.connect('192.168.2.99')
    try:
        if args.action=='stage':stage(client)
        else:run(client,args.action)
    finally:client.close()

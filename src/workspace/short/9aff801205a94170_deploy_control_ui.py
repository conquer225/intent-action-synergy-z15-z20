"""Prepare and install only the private interface; no hardware session is started."""
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time
from urllib.request import build_opener,ProxyHandler,Request
from PIL import Image
import numpy as np
import run_live_system as helpers
from system_hdmi import UnifiedDisplay

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'phone_video_upload/output/control_ui_20261008'
ASSETS=ROOT/'phone_video_upload/output/load_relief_20261007/menu_assets'


class Buffer(np.ndarray):
    def flush(self):pass


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(ROOT))
    display=UnifiedDisplay(ASSETS/'eye',live=True,dimensions=(288,512),
                           font_paths=(ASSETS/'cjk.ttf',ASSETS/'latin.ttf'))
    cache=OUT/'menu-shells-portrait-live.npz';display.save_shell_cache(cache)
    cached=UnifiedDisplay(ASSETS/'eye',live=True,dimensions=(288,512),
        font_paths=(ASSETS/'cjk.ttf',ASSETS/'latin.ttf'),shell_cache=cache)
    if any(not np.array_equal(display.shells[p],cached.shells[p]) for p in display.shells):
        raise ValueError('Menu cache roundtrip differs')
    from wheelchair_ssvep.dry_run_bridge import demo_snapshot
    now=time.monotonic();controller=display.controller
    buffer=np.empty((720,1280,3),dtype=np.uint8).view(Buffer)
    for name,frequency in (('drive-unselected',None),('drive-selected12',12)):
        controller._enter('drive',now);controller.presented(controller.page_id,now);now+=1.3
        if frequency is not None:
            controller.arm_virtual_direction(now);controller.ssvep(demo_snapshot(frequency),now)
        display.refresh_labels({}, {},'仅软件示意，非实际识别');display.compose(buffer,0,now=now)
        Image.fromarray(buffer[:,:,::-1]).save(OUT/(name+'.png'))
        now+=.1
    controller.monitor('fatigue','severe_candidate',now,source='manual_test',qualified=True)
    display.refresh_labels({}, {},'');display.compose(buffer,0,now=now)
    Image.fromarray(buffer[:,:,::-1]).save(OUT/'fatigue-locked.png')
    now+=.1;controller.monitor('fatigue',0,now,source='manual_test',qualified=True)
    display.refresh_labels({'fatigue':{'valid':True,'level':0}}, {},'');display.compose(buffer,0,now=now)
    Image.fromarray(buffer[:,:,::-1]).save(OUT/'fatigue-recovered.png')
    return cache


def main():
    cache=prepare();state=json.loads(helpers.STATE.read_text())
    c=helpers.upload.trial.connect('192.168.2.99')
    stage='/home/xilinx/gl-control-ui-'+time.strftime('%Y%m%d-%H%M%S')
    try:
        before=helpers.audit(c,state)
        if not before['release_unchanged']:raise ValueError('Formal baseline changed')
        execute=lambda command,root=False:helpers.execute(c,command,root)
        files=[]
        names=('media_server.py','media_player.py','player_commands.py','system_hdmi.py',
               'system_mobile.html','system_mobile.js','test_system_hdmi.py','test_media_server.py','test_player_commands.py')
        for name in names:files.append((ROOT/'phone_video_upload'/name,state['remote']+'/'+name))
        files.append((cache,state['remote']+'/'+cache.name))
        for name in ('core.py','live_inputs.py','page_policy.py','test_core.py','test_live_inputs.py'):
            files.append((ROOT/'guardianloop_system'/name,state['remote']+'/system_runtime/guardianloop_system/'+name))
        execute('mkdir -m 700 '+shlex.quote(stage));execute('mkdir -m 700 '+shlex.quote(stage+'/payload'))
        plan=dict(boot_id=before['boot'],pl=before['pl'],eye_root=state['eye_root'],
            manifest_sha=execute('sha256sum /home/xilinx/jupyter_notebooks/guardianloop_pynq/release_manifest.json').split()[0],files=[])
        with c.open_sftp() as ftp:
            ftp.put(str(ROOT/'phone_video_upload/control_ui_transaction.py'),stage+'/control_ui_transaction.py')
            for index,(local,target) in enumerate(files):
                key=str(index)+'-'+local.name
                old=execute('if test -f '+shlex.quote(target)+'; then sha256sum '+shlex.quote(target)+'; fi').split()
                new_sha=hashlib.sha256(local.read_bytes()).hexdigest()
                ftp.put(str(local),stage+'/payload/'+key)
                if execute('sha256sum '+shlex.quote(stage+'/payload/'+key)).split()[0]!=new_sha:
                    raise ValueError('Transfer mismatch')
                plan['files'].append(dict(key=key,target=target,old_sha=old[0] if old else None,new_sha=new_sha))
            with ftp.open(stage+'/plan.json','w') as stream:stream.write(json.dumps(plan))
        (OUT/'plan.json').write_text(json.dumps(plan,indent=2));(OUT/'before.json').write_text(json.dumps(before,indent=2))
        print(execute('env XILINX_XRT=/usr '+helpers.PYTHON+' '+shlex.quote(stage+'/control_ui_transaction.py')+' install',True),flush=True)
        with c.open_sftp() as ftp:
            for name in ('record.json','result.json'):ftp.get(stage+'/'+name,str(OUT/name))
        after=helpers.audit(c,state);(OUT/'after.json').write_text(json.dumps(after,indent=2))
        if before!=after:raise ValueError('Protected audit differs after private update')
        print('PRIVATE_UI_INSTALLED_NO_PL_OR_ACQUISITION_CHANGE',stage,flush=True)
    finally:c.close()


def verify_web():
    state=json.loads(helpers.STATE.read_text());c=helpers.upload.trial.connect('192.168.2.99')
    try:
        before=helpers.audit(c,state);helpers.server(c,state)
        opener=build_opener(ProxyHandler({}));rows={}
        for route in ('/','/system_mobile.js','/api/player'):
            request=Request('http://192.168.2.99:9117'+route,headers={'X-Media-Key':state['key']})
            with opener.open(request,timeout=5) as response:
                data=response.read();rows[route]=dict(status=response.status,cache=response.headers.get('Cache-Control'))
            if route=='/':
                if b'forceStop' not in data or b'ackFatigue' not in data:raise ValueError('Old UI response')
            elif route=='/system_mobile.js':
                if data!=(ROOT/'phone_video_upload/system_mobile.js').read_bytes():raise ValueError('Old script response')
            else:
                payload=json.loads(data)
                if not payload['silent'] or payload['player']['state']!='inactive':raise ValueError('Unexpected active display')
        after=helpers.audit(c,state)
        if before!=after:raise ValueError('Protected state changed while starting private web entry')
        result=dict(routes=rows,formal_state_unchanged=True,hdmi_started=False,pl_programmed=False,
                    private_server_temporary_minutes=40)
        (OUT/'web-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    finally:c.close()


if __name__=='__main__':
    if sys.argv[1:]==['verify']:verify_web()
    elif not sys.argv[1:]:main()
    else:raise ValueError('Only install or verify is supported')

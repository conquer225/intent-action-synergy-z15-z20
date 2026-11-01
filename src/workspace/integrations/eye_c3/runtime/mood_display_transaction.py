"""Pinned display-only transaction; restart the web service, never acquisition or PL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
from pynq import PL

APP=Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
MEDIA=Path('/home/xilinx/gl-media-20261007-314e8796')
GUARD=Path('/home/xilinx/brain_eye_coexist_20261005/eye/src/coexist_guard.py')
STARTUP=Path('/run/guardianloop-startup/status.json')
ALLOWED={APP/n for n in ('guardianloop_web.py','mobile.html','mobile.js','release_manifest.json')}
ALLOWED|={MEDIA/n for n in ('system_hdmi.py','system_mobile.js','menu-shells-portrait-live.npz')}
ALLOWED|={GUARD,STARTUP}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def service(name):
    raw=subprocess.check_output(['/bin/systemctl','show',name,'-p','MainPID','-p','ActiveState','-p','NRestarts'],text=True)
    return dict(line.split('=',1) for line in raw.splitlines())


def control(*args):subprocess.run(['/bin/systemctl',*args],check=True,timeout=20)


def replace(source,target,info):
    temporary=target.with_name(target.name+'.mood-new')
    shutil.copyfile(source,temporary)
    os.chown(temporary,*info[:2]);os.chmod(temporary,info[2]);temporary.replace(target)


def rollback(stage):
    record=json.loads((stage/'record.json').read_text())
    if record['phase']=='rolled_back':return
    for item in record['files']:
        target=Path(item['target'])
        if target not in ALLOWED or sha(target) not in (item['old_sha'],item['new_sha']):
            raise ValueError('Refusing to overwrite subsequent changes: '+str(target))
    for item in record['files']:
        replace(stage/'backup'/item['key'],Path(item['target']),item['info'])
    control('restart','guardianloop-web')
    record['phase']='rolled_back';(stage/'record.json').write_text(json.dumps(record,indent=2))


def install(stage):
    plan=json.loads((stage/'plan.json').read_text())
    cyton=service('guardianloop-cyton');web=service('guardianloop-web')
    if cyton['ActiveState']!='active' or web['ActiveState']!='active':raise ValueError('Services not ready')
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=plan['boot_id']:raise ValueError('Boot changed')
    if PL.bitfile_name!=plan['pl']:raise ValueError('Current PL changed')
    running=subprocess.run(['pgrep','-f','^'+sys.executable+' '+str(MEDIA/'media_player.py')],capture_output=True,text=True)
    if running.stdout.strip():raise ValueError('Do not replace panels during an active HDMI session')
    for route in ('/api/recording','/api/mi-cue','/api/ssvep-cue','/api/ssvep-free'):
        with urlopen('http://127.0.0.1:9102'+route,timeout=4) as response:value=json.load(response)
        if route=='/api/recording':value=value.get('recording',{})
        if value.get('state') in ('active','recording','starting','preparing','awaiting_presentation'):
            raise ValueError('Interactive session is active: '+route)
    manifest=json.loads((APP/'release_manifest.json').read_text())
    if sha(APP/'release_manifest.json')!=plan['previous_manifest_sha']:raise ValueError('Release changed')
    if not all(sha(APP/name)==digest for name,digest in manifest['files'].items()):raise ValueError('Baseline mismatch')
    backup=stage/'backup';backup.mkdir(mode=0o700)
    record=dict(phase='prepared',files=[],timer=stage.name+'-rollback')
    for item in plan['files']:
        target=Path(item['target']);incoming=stage/'new'/item['key']
        if target not in ALLOWED or sha(target)!=item['old_sha'] or sha(incoming)!=item['new_sha']:
            raise ValueError('Target or package changed: '+str(target))
        if target.suffix=='.py':compile(incoming.read_text(),str(target),'exec')
        stat=target.stat();item=dict(item,info=(stat.st_uid,stat.st_gid,stat.st_mode&0o777))
        shutil.copy2(target,backup/item['key']);record['files'].append(item)
    (stage/'record.json').write_text(json.dumps(record,indent=2))
    subprocess.run(['systemd-run','--unit='+record['timer'],'--on-active=120s',
        '--timer-property=AccuracySec=1s','env','XILINX_XRT=/usr',sys.executable,str(Path(__file__).resolve()),'rollback'],check=True,timeout=10)
    try:
        for item in record['files']:replace(stage/'new'/item['key'],Path(item['target']),item['info'])
        updated=json.loads((APP/'release_manifest.json').read_text())
        sys.path.insert(0,str(APP))
        from guardianloop_startup import verify_files
        count=verify_files(APP,updated)
        sys.path.insert(0,str(GUARD.parent))
        from coexist_guard import CoexistGuard
        admission=CoexistGuard(str(GUARD.parent.parent),plan['pl']).verify()
        sys.path.insert(0,str(MEDIA))
        from system_hdmi import UnifiedDisplay
        display=UnifiedDisplay(str(GUARD.parent.parent),live=True,dimensions=(288,512),
            shell_cache=MEDIA/'menu-shells-portrait-live.npz')
        control('restart','guardianloop-web')
        deadline=time.monotonic()+12
        while True:
            try:
                with urlopen('http://127.0.0.1:9102/healthz',timeout=2) as response:
                    if response.status!=200:raise ValueError('Web health check failed')
                break
            except URLError:
                if time.monotonic()>=deadline:raise
                time.sleep(.25)
        routes={}
        for route in ('/','/mobile','/mobile.js','/api/status'):
            with urlopen('http://127.0.0.1:9102'+route,timeout=4) as response:
                body=response.read();routes[route]=dict(status=response.status,cache=response.headers.get('Cache-Control'))
                if route=='/mobile.js' and hashlib.sha256(body).hexdigest()!=updated['files']['mobile.js']:
                    raise ValueError('Old mobile script response')
                if route=='/mobile' and '心情参考（模型估计）'.encode() not in body:
                    raise ValueError('Old mobile heading')
        if service('guardianloop-cyton')!=cyton:raise ValueError('Acquisition changed during display update')
        if PL.bitfile_name!=plan['pl']:raise ValueError('PL changed during display update')
        if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=plan['boot_id']:raise ValueError('Boot changed during update')
        if not all(sha(Path(i['target']))==i['new_sha'] for i in record['files']):raise ValueError('Install mismatch')
        result=dict(passed=True,release_id=updated['release_id'],verified_files=count,
            acquisition_unchanged=True,models_unchanged=True,pl_unchanged=True,boot_unchanged=True,
            cyton=cyton,web=service('guardianloop-web'),routes=routes,shells=len(display.shells),admission=admission,
            actual_HDMI_display_tested=False,backup=str(backup))
        record['phase']='verified';(stage/'record.json').write_text(json.dumps(record,indent=2))
        (stage/'result.json').write_text(json.dumps(result,indent=2))
        control('stop',record['timer']+'.timer')
        print(json.dumps(result),flush=True)
    except Exception:
        rollback(stage);control('stop',record['timer']+'.timer');raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('install','rollback'))
    args=parser.parse_args();stage=Path(__file__).resolve().parent
    if os.geteuid()!=0 or stage.parent!=Path('/home/xilinx') or not stage.name.startswith('gl-mood-display-'):
        raise ValueError('Run only the staged board-local transaction as root')
    globals()[args.action](stage)

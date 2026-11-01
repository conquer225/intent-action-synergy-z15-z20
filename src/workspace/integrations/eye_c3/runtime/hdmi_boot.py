"""Restore the standalone software entry and static HDMI home without flicker."""
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.error

from hdmi_live_session import BASE, OVERRIDE, SERVICE, activate, run


def verified_state(base, boot, pid, hashes):
    state=json.loads((base/'state.json').read_text())
    if state['remote']!=str(base) or state.get('user_controlled') is not True:
        raise ValueError('Only this explicitly user-controlled entry may resume')
    for name,digest in hashes.items():
        path=Path(name)
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Boot entry artifact changed: '+name)
    return dict(state,boot=boot,before_pid=pid)


def wait_local_network(timeout=45):
    deadline=time.monotonic()+timeout
    while True:
        addresses=json.loads(run('ip','-j','-4','addr','show','up'))
        if any(a.get('scope')=='global' for interface in addresses for a in interface.get('addr_info',[])):
            return
        if time.monotonic()>=deadline:
            raise ValueError('本地网络未就绪；未加载 PL 或启动刺激')
        time.sleep(.5)


def start_static_home(timeout=20):
    url='http://127.0.0.1:9119'
    key=(BASE/'access.key').read_text().strip()
    deadline=time.monotonic()+timeout
    while True:
        request=urllib.request.Request(url+'/api/player',data=b'{"action":"display_start"}',
            headers={'X-Media-Key':key,'Origin':url,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=3) as response:
                if response.status!=202:raise ValueError('Static-home entry was not acknowledged')
                return json.loads(response.read())
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError:
            if time.monotonic()>=deadline:raise
            time.sleep(.5)


def main():
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    pins=json.loads((BASE/'boot-pins.json').read_text())
    original=json.loads((BASE/'state.json').read_text())
    pid=int(run('systemctl','show',SERVICE,'-p','MainPID','--value'))
    if not pid:raise ValueError('Formal acquisition must start first')
    state=verified_state(BASE,boot,pid,pins['files'])
    server=BASE.name+'-server.service'
    if (original['boot']==boot and OVERRIDE.is_file()
            and OVERRIDE.read_text()==original['override_text']
            and int(run('systemctl','show',server,'-p','MainPID','--value') or 0)>0):
        print('CURRENT_BOOT_ENTRY_UNCHANGED_NO_RESTART',flush=True)
        return
    if OVERRIDE.exists():raise ValueError('Another override exists; do not replace it')
    wait_local_network()
    # Keep previous session diagnostics; do not adopt an old boot's player.
    for name in ('activated.json','player_status.json','restoration.json') if original['boot']!=boot else ():
        path=BASE/name
        if path.exists():path.rename(BASE/(name+'.boot-'+original['boot']))
    media=json.loads((BASE/'media_state.json').read_text())
    media['boot']=boot
    for name,row in (('state.json',state),('media_state.json',media)):
        path=BASE/name;temporary=path.with_suffix('.boot-new')
        temporary.write_text(json.dumps(row,indent=2));temporary.chmod(0o600);temporary.replace(path)
    # The pinned media configuration changes only its verified boot identity here.
    media_path=BASE/'media_state.json'
    pins['files'][str(media_path)]=hashlib.sha256(media_path.read_bytes()).hexdigest()
    pin_path=BASE/'boot-pins.json';temporary=pin_path.with_suffix('.boot-new')
    temporary.write_text(json.dumps(pins,indent=2));temporary.chmod(0o600);temporary.replace(pin_path)
    activate(state,BASE/'state.json')
    result=start_static_home()
    print('PRIVATE_ENTRY_RESUMED_STATIC_HOME_NO_FLICKER_NO_AUDIO_NO_MOTOR '+json.dumps(result),flush=True)


if __name__=='__main__':main()

"""Bounded display update with the existing checksummed installer and rollback."""
import json
import re
from pathlib import Path
import subprocess
import time
from urllib.request import Request,urlopen

BASE=Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')
SERVER=BASE.name+'-server.service'
PYTHON='/usr/local/share/pynq-venv/bin/python3'


def control(*args):
    return subprocess.run(['systemctl',*args],check=True,capture_output=True,text=True,timeout=20).stdout.strip()


def stop_server():
    if control('show',SERVER,'-p','LoadState','--value')!='not-found':
        control('stop',SERVER)


def start_server():
    if control('show',SERVER,'-p','LoadState','--value')!='not-found':
        control('start',SERVER)
        return
    state=json.loads((BASE/'state.json').read_text())
    lifetime=[] if state.get('user_controlled') is True else ['--property=RuntimeMaxSec=570s']
    subprocess.run(['systemd-run','--unit='+BASE.name+'-server',*lifetime,
        '--property=TimeoutStopSec=10s','--property=MemoryMax=384M',
        '--property=Nice=5','--property=LimitCORE=0','env','XILINX_XRT=/usr',
        'OPENBLAS_NUM_THREADS=1',PYTHON,str(BASE/'media_server.py'),
        '--key-file',str(BASE/'access.key'),'--port','9119'],
        check=True,capture_output=True,text=True,timeout=20)


def api(body=None):
    base='http://127.0.0.1:9119'
    key=(BASE/'access.key').read_text().strip()
    with urlopen(Request(base+'/api/player',data=json.dumps(body).encode() if body is not None else None,
        headers={'X-Media-Key':key,'Origin':base,'Content-Type':'application/json'}),timeout=5) as response:
        return json.load(response)


def stop_display():
    try:row=api()['player']
    except OSError:
        row=json.loads((Path('/dev/shm')/(BASE.name+'-player-status.json')).read_text())
    ident=row.get('session_id','')
    if not re.fullmatch('play-[a-f0-9]{8}',ident):raise ValueError('Unknown display owner')
    if control('show',ident+'.service','-p','MainPID','--value')=='0':return
    try:api({'action':'stop'})
    except OSError:control('stop',ident+'.service')
    deadline=time.monotonic()+35
    while control('show',ident+'.service','-p','MainPID','--value')!='0':
        if time.monotonic()>deadline:raise TimeoutError('Display still owns buffers; do not replace it')
        time.sleep(.3)
    report=json.loads((BASE/(ident+'-report.json')).read_text())
    if not report.get('original_restored') or not report.get('buffers_released'):
        raise RuntimeError('Display recovery was not verified')


def start_home():
    start_server()
    deadline=time.monotonic()+35
    while True:
        try:api({'action':'display_start'});break
        except OSError:
            if time.monotonic()>deadline:raise
            time.sleep(.3)
    while True:
        row=api();player=row['player'];system=player.get('system') or {}
        if player['state']=='error':raise RuntimeError(player.get('error'))
        if player['state']=='menu' and system.get('page')=='home':return row
        if time.monotonic()>deadline:raise TimeoutError('Static home did not acknowledge')
        time.sleep(.3)


def main():
    stage=Path(__file__).resolve().parent;plan=json.loads((stage/'guard-plan.json').read_text())
    if plan['boot']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        raise ValueError('Boot changed; do not reuse this update plan')
    before_pid=control('show','guardianloop-cyton.service','-p','MainPID','--value')
    report={'before_acquisition_pid':before_pid,'source':'display_update_no_live_eeg_simulation'}
    installed=False
    try:
        stop_display();stop_server()
        subprocess.run([PYTHON,str(stage/'drive_navigation_install.py'),'install'],check=True,timeout=30)
        installed=True
        row=start_home();system=row['player']['system']
        if system['physical_output_enabled'] is not False or row.get('auto_hdmi_on_drive') is not True:
            raise ValueError('Updated home contract did not verify')
        after_pid=control('show','guardianloop-cyton.service','-p','MainPID','--value')
        if after_pid!=before_pid:raise RuntimeError('Acquisition changed during display update')
        report.update(state='installed_static_home',session=row['player']['session_id'],
                      after_acquisition_pid=after_pid,physical_output_enabled=False)
    except BaseException as error:
        report.update(state='failed',error=str(error))
        record=stage/'guard-installation.json'
        phase=json.loads(record.read_text()).get('phase') if record.exists() else None
        if installed or phase in ('backed_up','installed'):
            stop_display();stop_server()
            subprocess.run([PYTHON,str(stage/'drive_navigation_install.py'),'rollback'],check=True,timeout=30)
        row=start_home();report.update(restored_home_session=row['player']['session_id'])
        raise
    finally:
        (stage/'apply-result.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report),flush=True)


if __name__=='__main__':main()

"""Return this finite private trial to the previously stopped static HDMI entry."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
PRODUCTION = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')


def may_restore(report, current_session, previous_session):
    return (report.get('original_restored') is True
            and report.get('buffers_released') is True
            and current_session == previous_session)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--previous-session', required=True)
    args = parser.parse_args()
    if args.state.resolve().parent != ROOT:
        raise ValueError('Foreign private session')
    state = json.loads(args.state.read_text())
    report = json.loads((ROOT/(state['session_id']+'-report.json')).read_text())
    previous = json.loads((PRODUCTION/'player_status.json').read_text())
    if not may_restore(report, previous.get('session_id'), args.previous_session):
        raise RuntimeError('Trial cleanup incomplete or another normal session has taken ownership')
    for unit in (state['hardware_unit'], args.previous_session+'.service'):
        pid = subprocess.run(['systemctl','show',unit,'-p','MainPID','--value'],
                             check=True,capture_output=True,text=True,timeout=10).stdout.strip()
        if int(pid or '0'):
            raise RuntimeError('Display is still owned; no replacement was started')
    key = (PRODUCTION/'access.key').read_text().strip()
    base = 'http://127.0.0.1:9119'

    def request(body):
        data = json.dumps(body).encode() if body else None
        headers = {'X-Media-Key':key,'Origin':base,'Content-Type':'application/json'}
        with urllib.request.urlopen(urllib.request.Request(base+'/api/player',data=data,
                                                          headers=headers),timeout=5) as response:
            return json.loads(response.read())

    session = request({'action':'play','id':'sd02'})['session_id']
    deadline = time.monotonic()+30
    while time.monotonic() < deadline:
        player = request(None)['player']
        if player.get('session_id') == session and player.get('system'):
            receipt = request({'action':'force_stop'})
            break
        time.sleep(.5)
    else:
        raise RuntimeError('Normal HDMI startup has not acknowledged; inspect its report')
    deadline = time.monotonic()+15
    while time.monotonic() < deadline:
        player = request(None)['player']
        acknowledged = player.get('command_receipt') or {}
        system = player.get('system') or {}
        if (player.get('session_id') == session and system.get('page') == 'home'
                and acknowledged.get('id') == receipt['command_id']
                and acknowledged.get('state') == 'applied'):
            print(json.dumps({'static_session':session,'page':'home','confirmed':True}),flush=True)
            return
        time.sleep(.5)
    raise RuntimeError('Static-home command did not acknowledge; no completion was claimed')


if __name__ == '__main__':
    main()

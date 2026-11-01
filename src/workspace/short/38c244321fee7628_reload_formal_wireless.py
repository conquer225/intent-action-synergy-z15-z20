"""Use the saved board Wi-Fi profile briefly; restore the PC's Internet Wi-Fi."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
from pathlib import Path
import shlex
import re
import socket
import subprocess
import sys
import time

from run_soak_stage import connect, command
from run_ssvep_backlog_replay import checked

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT/'eeg_apps_z15/output/ssvep_free_study_20261003/package'
REMOTE_PYTHON = '/usr/local/share/pynq-venv/bin/python3'
HOST = '192.168.50.1'
APP = '/home/xilinx/jupyter_notebooks/guardianloop_pynq/'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def netsh(profile):
    result = subprocess.run(['netsh', 'wlan', 'connect', 'name='+profile, 'interface=WLAN'],
                            capture_output=True, timeout=10)
    if result.returncode:
        raise RuntimeError('Wi-Fi profile connection request failed')


def wait_board():
    deadline = time.monotonic()+30
    while True:
        try:
            interfaces = subprocess.check_output(['netsh','wlan','show','interfaces'], timeout=5).decode(errors='replace')
            addresses = subprocess.check_output(['netsh','interface','ipv4','show','addresses','name=WLAN'], timeout=5).decode(errors='replace')
            if (re.search(r'^\s*SSID\s*:\s*GuardianLoop-Z15\s*$', interfaces, re.M)
                    and re.search(r'192\.168\.50\.\d+', addresses)):
                with socket.create_connection((HOST, 22), timeout=1):
                    print('Z15_WIFI_AND_ADDRESS_READY', flush=True)
                    return
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Z15 hotspot SSH not reachable')
        time.sleep(.5)


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def expected(boot):
    manifest = json.loads((PACKAGE/'runtime/release_manifest.json').read_text())
    ledger = json.loads((PACKAGE/'transaction.json').read_text())
    guard = dict(ledger['protected'])
    guard.update({path:row['new_sha256'] for path,row in ledger['targets'].items()})
    guard.update({APP+name:value for name,value in manifest['files'].items()})
    guard[APP+'release_manifest.json'] = digest(PACKAGE/'runtime/release_manifest.json')
    for name,value in manifest['files'].items():
        if digest(PACKAGE/'runtime'/name) != value:
            raise ValueError('Frozen local recovery package changed: '+name)
    return dict(boot_id=boot, manifest=manifest, guard=guard)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'launch', 'status', 'verify'))
    parser.add_argument('--previous-profile', default='JLU.WIFI')
    parser.add_argument('--boot-id')
    parser.add_argument('--state', type=Path)
    args = parser.parse_args()
    if args.previous_profile == 'GuardianLoop-Z15':
        raise ValueError('An Internet profile is needed for automatic connection restoration')
    if args.action == 'stage':
        if not args.boot_id:
            raise ValueError('Requires boot ID verified over the known board serial port')
        stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
        output = ROOT/'eeg_apps_z15/output'/('formal_wireless_reload_'+stamp)
        output.mkdir()
        record = dict(host=HOST, previous_profile=args.previous_profile, output=str(output))
        frozen = expected(args.boot_id)
    else:
        if not args.state:
            raise ValueError('Requires the saved stage state')
        record = json.loads(args.state.read_text())
        output = Path(record['output'])
    client = None
    try:
        netsh('GuardianLoop-Z15')
        wait_board()
        client = connect(HOST)
        if args.action == 'stage':
            stage = command(client, 'mktemp -d /home/xilinx/formal-reload-XXXXXX').strip()
            if not stage.startswith('/home/xilinx/formal-reload-') or '/' in stage[len('/home/xilinx/'):]:
                raise ValueError('Unexpected stage directory')
            record['remote'] = stage
            dump(output/'expected.json', frozen)
            with client.open_sftp() as sftp:
                sftp.mkdir(stage+'/runtime')
                sftp.put(str(output/'expected.json'), stage+'/expected.json')
                sftp.put(str(Path(__file__).with_name('reload_formal_board.py')), stage+'/reload_formal_board.py')
            invocation = REMOTE_PYTHON+' '+shlex.quote(stage+'/reload_formal_board.py')+' audit --stage '+shlex.quote(stage)
            before = json.loads(command(client, invocation))
            dump(output/'preflight.json', before)
            with client.open_sftp() as sftp:
                for name in (*frozen['manifest']['files'], 'release_manifest.json'):
                    sftp.put(str(PACKAGE/'runtime'/name), stage+'/runtime/'+name)
            record['phase'] = 'staged'
            dump(output/'state.json', record)
            print(json.dumps(dict(phase='staged', release=before['release'],
                                 files=before['files'], state=str(output/'state.json'))), flush=True)
        elif args.action == 'launch':
            if record['phase'] != 'staged':
                raise ValueError('Reload is only allowed once per stage')
            stage = record['remote']
            shell = ('nohup timeout 180s env XILINX_XRT=/usr OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 '
                +REMOTE_PYTHON+' '+shlex.quote(stage+'/reload_formal_board.py')+' reload --stage '
                +shlex.quote(stage)+' >'+shlex.quote(stage+'/run.log')+' 2>&1 </dev/null & echo $!')
            pid = checked(client, 'sh -c '+shlex.quote(shell), sudo=True).strip()
            record.update(phase='launched', pid=pid)
            # State is an operational ledger, not an immutable result artifact.
            args.state.write_text(json.dumps(record, indent=2), encoding='utf-8')
            print(json.dumps(dict(phase='launched', pid=pid, remote=stage)), flush=True)
        elif args.action == 'verify':
            stage = record['remote']
            with client.open_sftp() as sftp:
                sftp.put(str(Path(__file__).with_name('verify_formal_reload_board.py')), stage+'/verify_formal_reload_board.py')
            # Reparse the unchanged protected units after the explicit application reload.
            checked(client, 'systemctl daemon-reload', sudo=True)
            invocation = REMOTE_PYTHON+' '+shlex.quote(stage+'/verify_formal_reload_board.py')+' --stage '+shlex.quote(stage)
            print(command(client, invocation), flush=True)
            with client.open_sftp() as sftp:
                if (output/'verification.json').exists():
                    raise ValueError('Preserve existing final verification')
                sftp.get(stage+'/verification.json', str(output/'verification.json'))
            record['phase'] = 'verified_after_identical_recovery'
            args.state.write_text(json.dumps(record,indent=2),encoding='utf-8')
        else:
            downloaded = {}
            with client.open_sftp() as sftp:
                for name in ('result.json', 'run.log'):
                    destination = output/(name if not (output/name).exists()
                        else name+'.'+datetime.now().strftime('%H%M%S'))
                    sftp.get(record['remote']+'/'+name, str(destination))
                    downloaded[name] = destination
            result = json.loads(downloaded['result.json'].read_text())
            print(json.dumps(dict(passed=result['passed'], stage=result['stage'],
                error=result.get('error'), result=str(downloaded['result.json']))), flush=True)
    finally:
        if client is not None:
            client.close()
        netsh(args.previous_profile)
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            info = subprocess.check_output(['netsh','wlan','show','interfaces'], timeout=5).decode(errors='replace')
            if re.search(r'^\s*SSID\s*:\s*'+re.escape(args.previous_profile)+r'\s*$',info,re.M):
                print('PC_WIFI_RESTORED', flush=True)
                break
            time.sleep(.5)
        else:
            raise RuntimeError('PC Wi-Fi restoration not confirmed')


if __name__ == '__main__':
    transport_log = logging.getLogger('paramiko.transport')
    transport_log.addHandler(logging.NullHandler())
    transport_log.propagate = False
    try:
        main()
    except Exception as exc:
        print(type(exc).__name__+': '+str(exc), file=sys.stderr)
        raise SystemExit(1)

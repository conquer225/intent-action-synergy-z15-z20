"""Audit, then deploy only the explicitly authorized mobile web files."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

sys.path.append(r'D:\Users\lenovo\anaconda3\Lib\site-packages')
from reload_formal_wireless import netsh, wait_board
from run_soak_stage import connect
from run_ssvep_backlog_replay import checked

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'eeg_apps_z15/output/ssvep_free_study_20261003/package'
APP = '/home/xilinx/jupyter_notebooks/guardianloop_pynq/'
PYTHON = '/usr/bin/python3'
WORKER = Path(__file__).with_name('mobile_web_transaction.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args()
    output = ROOT/'eeg_apps_z15/output'/('mobile_web_deploy_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    output.mkdir()
    interface = subprocess.check_output(['netsh','wlan','show','interfaces'], text=True, errors='replace')
    match = re.search(r'^\s*Profile\s*:\s*(.+?)\s*$', interface, re.M)
    if not match:
        raise RuntimeError('Cannot determine Wi-Fi profile for restoration')
    previous = match.group(1)
    client = None
    try:
        if previous != 'GuardianLoop-Z15':
            netsh('GuardianLoop-Z15')
        wait_board()
        client = connect('192.168.50.1')
        old = json.loads((BASE/'runtime/release_manifest.json').read_text())
        ledger = json.loads((BASE/'transaction.json').read_text())
        guard = dict(ledger['protected'])
        guard.update({path:value['new_sha256'] for path,value in ledger['targets'].items()})
        guard.update({APP+name:value for name,value in old['files'].items()})
        guard[APP+'release_manifest.json'] = digest(BASE/'runtime/release_manifest.json')
        guard['/etc/default/guardianloop-mi.json'] = 'd04a75314cdc173966a098cfdbe83b107b1427c8625814855cce326d54fcee9a'
        guard['/etc/systemd/system/guardianloop-startup.service'] = '4d37a59bbf463f95d1801c2b48f2b1f91b12a05898b865c6c5ac1b083230c9f2'
        source = WORKER.read_text()
        probe = "import json; scope={'__name__':'mobile_audit'}; exec(%r,scope); print(json.dumps(scope['audit'](%r)))" % (source, list(guard))
        before = json.loads(checked(client, PYTHON+' -c '+shlex.quote(probe)))
        save(output/'preflight.json', before)
        if before['hashes'] != guard or before['manifest'] != old:
            mismatch = [name for name,value in guard.items() if before['hashes'].get(name) != value]
            raise RuntimeError('Baseline differs; preserved board files: '+str(mismatch))
        if before['startup']['state'] != 'ready' or before['startup']['boot_id'] != before['boot_id']:
            raise RuntimeError('Current boot self-test is not ready')
        if any(before['existing_mobile'].values()):
            raise RuntimeError('Unexpected existing mobile files; do not overwrite')
        # Reuse the board worker's exact idle check without executing its main.
        namespace = {'__name__':'mobile_transaction_audit'}
        exec(compile(source, str(WORKER), 'exec'), namespace)
        namespace['idle'](before)
        print(json.dumps(dict(phase='audit_passed', boot_id=before['boot_id'],
            cyton=before['cyton'], web=before['web'], sessions=before['sessions'],
            protected_files=len(guard), output=str(output))), flush=True)
        if args.audit_only:
            return
        runtime = output/'runtime'
        runtime.mkdir()
        for name in ('guardianloop_web.py','mobile.html','mobile.js'):
            original = ROOT/'pynq_guardianloop'/name
            (runtime/name).write_bytes(original.read_bytes())
        new = dict(old)
        new['files'] = dict(old['files'])
        new['previous_release_id'] = old['release_id']
        new['release_id'] = 'guardianloop-fixed8-mobile-web-20261003'
        for name in ('guardianloop_web.py','mobile.html','mobile.js'):
            new['files'][name] = digest(runtime/name)
        new['mobile_web'] = dict(path='/mobile', android_device_verified=False,
            ssvep_stimulus_enabled=False, background_monitoring=False, model_changes=False)
        save(runtime/'release_manifest.json', new)
        expected = dict(before=before, guard=guard, release_id=new['release_id'],
            new_hashes={name:digest(runtime/name) for name in namespace['TARGETS']})
        save(output/'expected.json', expected)
        stage = checked(client, 'mktemp -d /home/xilinx/mobile-web-XXXXXX').strip()
        if not re.fullmatch(r'/home/xilinx/mobile-web-[A-Za-z0-9]+', stage):
            raise RuntimeError('Invalid stage path')
        save(output/'state.json', dict(remote=stage, host='192.168.50.1', output=str(output)))
        with client.open_sftp() as sftp:
            sftp.mkdir(stage+'/new')
            sftp.put(str(output/'expected.json'), stage+'/expected.json')
            sftp.put(str(WORKER), stage+'/worker.py')
            for path in runtime.iterdir():
                sftp.put(str(path), stage+'/new/'+path.name)
        invocation = 'nohup '+PYTHON+' '+shlex.quote(stage+'/worker.py')+' --stage '+shlex.quote(stage)+' >'+shlex.quote(stage+'/run.log')+' 2>&1 </dev/null &'
        checked(client, 'sh -c '+shlex.quote(invocation), sudo=True)
        deadline = time.monotonic()+100
        with client.open_sftp() as sftp:
            while True:
                try:
                    with sftp.open(stage+'/result.json') as stream:
                        result = json.load(stream)
                    break
                except FileNotFoundError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Transaction not yet complete; inspect '+stage)
                    time.sleep(1)
            save(output/'result.json', result)
            sftp.get(stage+'/run.log', str(output/'run.log'))
            if result['passed'] or result['phase'] == 'rolled_back':
                backup = output/'backup'
                backup.mkdir()
                for name in ('guardianloop_web.py','release_manifest.json'):
                    sftp.get(stage+'/backup/'+name, str(backup/name))
        print(json.dumps(dict(passed=result['passed'], phase=result['phase'], error=result.get('error'),
            output=str(output), remote=stage, release=new['release_id'])), flush=True)
    finally:
        if client is not None:
            client.close()
        if previous != 'GuardianLoop-Z15':
            netsh(previous)
            deadline = time.monotonic()+15
            while time.monotonic() < deadline:
                text = subprocess.check_output(['netsh','wlan','show','interfaces'], text=True, errors='replace')
                if re.search(r'^\s*SSID\s*:\s*'+re.escape(previous)+r'\s*$', text, re.M):
                    print('PC_WIFI_RESTORED', flush=True)
                    break
                time.sleep(.5)
            else:
                raise RuntimeError('PC Wi-Fi restoration not confirmed')


if __name__ == '__main__':
    main()

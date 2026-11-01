"""Verify reader-level MI fan-out using Linux pipes, then patch only the live sandbox."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import time

from run_soak_stage import connect
from run_ssvep_backlog_replay import checked
from deploy_mi_live_virtual import protect, FORMAL

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'eeg_apps_z15/output/mi_live_virtual_20261003'
LIVE = '/home/xilinx/mi-live-virtual-20261003-a1'
CHECK = '/home/xilinx/mi-reader-tap-check-20261003-a1'
CHANGED = ('cyton_guardianloop.py', 'mi_acquisition.py')
TESTS = ('test_mi_reader_tap.py', 'test_cyton_reader_faults.py', 'test_mi_acquisition.py',
         'test_mi_cued.py', 'test_mi_virtual.py', 'test_mi_formal_entry.py', 'mi_reader_tap_smoke.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(sftp, path):
    with sftp.open(path, 'rb') as stream:
        return json.loads(stream.read())


def snapshot(client):
    code = ("import json; from urllib.request import urlopen; "
            "print(json.dumps(json.load(urlopen('http://127.0.0.1:9102/api/mi-cue',timeout=2))))")
    return json.loads(checked(client, 'python3 -c '+shlex.quote(code)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deploy', action='store_true')
    args = parser.parse_args()
    client = connect()
    installed = False
    try:
        with client.open_sftp() as sftp:
            previous = json.loads((OUT / 'DEPLOYMENT.json').read_text(encoding='utf-8'))
            formal_release = read_json(sftp, FORMAL+'/release_manifest.json')
            before = protect(client, sftp, formal_release)
            checked(client, 'test ! -e '+CHECK+' && mkdir '+CHECK)
            originals = {}
            for name, expected in previous['files'].items():
                with sftp.open(LIVE+'/'+name, 'rb') as stream:
                    data = stream.read()
                if sha(data) != expected:
                    raise RuntimeError('Live sandbox changed since installation: '+name)
                with sftp.open(CHECK+'/'+name, 'wb') as stream:
                    stream.write(data)
                if name in CHANGED:
                    originals[name] = data
            with sftp.open(LIVE+'/release_manifest.json', 'rb') as stream:
                originals['release_manifest.json'] = stream.read()
            candidate = json.loads(originals['release_manifest.json'])
            for name in (*CHANGED, *TESTS):
                source = ROOT/'pynq_guardianloop'/name
                sftp.put(str(source), CHECK+'/'+name)
                if name in CHANGED:
                    candidate['files'][name] = sha(source.read_bytes())
            env = 'env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH='+shlex.quote(CHECK)+' '
            prefix = 'cd '+CHECK+' && '+env+'/usr/local/share/pynq-venv/bin/python3 '
            print('Checking MI fan-out and existing reader fault recovery; no USB/PL access', flush=True)
            log = checked(client, 'timeout 60s sh -c '+shlex.quote(prefix+'-m unittest '
                'test_mi_reader_tap test_cyton_reader_faults test_mi_acquisition '
                'test_mi_cued test_mi_virtual test_mi_formal_entry'))
            (OUT/'reader_tap_arm_tests.log').write_text(log, encoding='utf-8')
            print('ARM regression passed; testing model while primary pipe consumer is paused', flush=True)
            smoke_log = checked(client, 'timeout 30s sh -c '+shlex.quote(prefix+
                'mi_reader_tap_smoke.py --model experimental_eegnet.npz --output tap-smoke.json'))
            (OUT/'reader_tap_smoke.log').write_text(smoke_log, encoding='utf-8')
            smoke = read_json(sftp, CHECK+'/tap-smoke.json')
            if not smoke['passed'] or protect(client, sftp, formal_release) != before:
                raise RuntimeError('Smoke/protected-file verification failed')
            evidence = dict(check_stage=CHECK, smoke=smoke,
                before=before, files=candidate['files'], deployed=False, formal_unchanged=True)
            (OUT/'READER_TAP_VERIFICATION.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
            if not args.deploy:
                print(json.dumps(smoke)); return
            if read_json(sftp, '/run/guardianloop/recording_status.json').get('state') == 'recording':
                raise RuntimeError('Do not interrupt an active human recording')
            for _ in range(10):
                current = snapshot(client)
                if current.get('state') not in ('active', 'awaiting_presentation'):
                    break
                time.sleep(1)
            else:
                raise RuntimeError('An MI trial is active; stop it before restarting')
            for name, data in originals.items():
                with sftp.open(LIVE+'/'+name, 'rb') as stream:
                    if stream.read() != data:
                        raise RuntimeError('Live sandbox was modified during verification: '+name)
                with sftp.open(CHECK+'/'+name+'.original', 'wb') as stream:
                    stream.write(data)
            print('Restarting only the temporary Cyton service; formal files and PL unchanged', flush=True)
            checked(client, 'systemctl stop guardianloop-cyton.service', sudo=True)
            installed = True
            candidate.update(mi_input_route='bounded_serial_reader_tap_to_MI_process',
                             freshness_seconds=.5, warmup_samples=500)
            with sftp.open(CHECK+'/release_manifest.json', 'w') as stream:
                stream.write(json.dumps(candidate, indent=2))
            for name in (*CHANGED, 'release_manifest.json'):
                checked(client, 'install -m 644 '+CHECK+'/'+name+' '+LIVE+'/'+name, sudo=True)
            checked(client, 'systemctl start guardianloop-cyton.service', sudo=True)
            for _ in range(25):
                time.sleep(1)
                current = snapshot(client)
                if current.get('input_state') == 'ready':
                    break
            else:
                raise RuntimeError('Updated live route did not warm up')
            if current['source']!='live' or current['control_enabled'] or current['production_eligible']:
                raise RuntimeError('Unexpected live candidate identity')
            after = protect(client, sftp, formal_release)
            if after != before:
                raise RuntimeError('Formal files/config/boot identity changed')
            evidence.update(deployed=True, after=after, live_snapshot=current,
                            services=checked(client,'systemctl is-active guardianloop-cyton.service guardianloop-web.service'))
            (OUT/'READER_TAP_DEPLOYMENT.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
            print(json.dumps(dict(deployed=True, formal_unchanged=True, smoke=smoke,
                                  live=current)), flush=True)
    except BaseException:
        if installed:
            print('Restoring previous sandbox files and restarting the service', flush=True)
            checked(client, 'systemctl stop guardianloop-cyton.service', sudo=True)
            for name in (*CHANGED, 'release_manifest.json'):
                checked(client,'install -m 644 '+CHECK+'/'+name+'.original '+LIVE+'/'+name,sudo=True)
            checked(client,'systemctl start guardianloop-cyton.service',sudo=True)
        raise
    finally:
        client.close()


if __name__ == '__main__':
    main()

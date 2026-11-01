"""Temporarily run the accepted virtual MI candidate on real Cyton input.

Only /run systemd overrides are installed. Formal code, opt-in, model, PL,
and boot files stay unchanged. --restore withdraws these exact overrides.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import time

from run_soak_stage import connect
from run_ssvep_backlog_replay import checked

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'eeg_apps_z15/output/mi_live_virtual_20261003'
ASSETS = OUT / 'runtime'
FORMAL = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
STAGE = '/home/xilinx/mi-live-virtual-20261003-a1'
OVERRIDES = {
    'cyton.conf': '/run/systemd/system/guardianloop-cyton.service.d/90-mi-live-virtual.conf',
    'web.conf': '/run/systemd/system/guardianloop-web.service.d/90-mi-live-virtual.conf',
}
UNITS = 'guardianloop-cyton.service guardianloop-web.service'
CANDIDATE_FILES = ('mi_cued.py', 'mi_cued.html', 'mi_web_bridge.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(sftp, path):
    with sftp.open(path, 'rb') as stream:
        return json.loads(stream.read())


def protect(client, sftp, release):
    paths = [FORMAL + '/' + name for name in release['files']]
    paths += [FORMAL + '/release_manifest.json', '/etc/default/guardianloop-mi.json']
    hashes = checked(client, 'sha256sum ' + ' '.join(map(shlex.quote, paths)))
    services = checked(client, 'find /etc/systemd/system/guardianloop-cyton.service '
                       '/etc/systemd/system/guardianloop-cyton.service.d '
                       '/etc/systemd/system/guardianloop-web.service '
                       '/etc/systemd/system/guardianloop-web.service.d '
                       "-type f -exec sha256sum {} \\;")
    return dict(hashes=hashes, service_files=services,
                mi_config=read_json(sftp, '/etc/default/guardianloop-mi.json'),
                boot_id=checked(client, 'cat /proc/sys/kernel/random/boot_id').strip())


def restore(client):
    # Refuse to remove an override that another operator changed.
    for name, destination in OVERRIDES.items():
        expected = digest((ASSETS / name).read_bytes())
        checked(client, 'test ! -e ' + shlex.quote(destination) + ' || test "$(sha256sum '
                + shlex.quote(destination) + ' | cut -d\' \' -f1)" = ' + expected, sudo=True)
    checked(client, 'systemctl stop ' + UNITS, sudo=True)
    for destination in OVERRIDES.values():
        checked(client, 'rm -f -- ' + shlex.quote(destination), sudo=True)
    checked(client, 'systemctl daemon-reload', sudo=True)
    checked(client, 'systemctl start ' + UNITS, sudo=True)
    return checked(client, 'systemctl is-active ' + UNITS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    client = connect()
    changed = False
    try:
        with client.open_sftp() as sftp:
            if args.restore:
                print(restore(client))
                return
            release = read_json(sftp, FORMAL + '/release_manifest.json')
            before = protect(client, sftp, release)
            if before['mi_config'] != {'enabled': False}:
                raise RuntimeError('Formal MI opt-in is not off; inspect before changing runtime')
            recording = read_json(sftp, '/run/guardianloop/recording_status.json')
            if recording.get('state') == 'recording':
                raise RuntimeError('An active human recording must not be interrupted')
            checked(client, 'test ! -e ' + STAGE)
            for destination in OVERRIDES.values():
                checked(client, 'test ! -e ' + shlex.quote(destination))
            checked(client, 'mkdir ' + STAGE)
            files = {}
            # Stage exact current dependencies; never invoke Overlay or startup.
            for name in (*release['files'], 'gameemo_emotion_model.json'):
                with sftp.open(FORMAL + '/' + name, 'rb') as stream:
                    data = stream.read()
                if name in release['files'] and digest(data) != release['files'][name]:
                    raise RuntimeError('Formal artifact differs from manifest: ' + name)
                with sftp.open(STAGE + '/' + name, 'wb') as stream:
                    stream.write(data)
                files[name] = digest(data)
            accepted = json.loads((OUT.parent / 'mi_virtual_control_20261003/VERIFICATION.json')
                                  .read_text(encoding='utf-8'))
            for name in CANDIDATE_FILES:
                data = (ROOT / 'pynq_guardianloop' / name).read_bytes()
                if digest(data) != accepted['code_sha256'][name]:
                    raise RuntimeError('Candidate changed since verification: ' + name)
                sftp.put(str(ROOT / 'pynq_guardianloop' / name), STAGE + '/' + name)
                files[name] = digest(data)
            for path in ASSETS.iterdir():
                sftp.put(str(path), STAGE + '/' + path.name)
                files[path.name] = digest(path.read_bytes())
            for name in ('test_mi_formal_entry.py', 'test_mi_cued.py', 'test_mi_virtual.py'):
                sftp.put(str(ROOT / 'pynq_guardianloop' / name), STAGE + '/' + name)
            candidate_release = dict(release, release_id='mi-live-virtual-20261003-runtime-only',
                                     base_release_id=release['release_id'],
                                     temporary=True, files=files)
            with sftp.open(STAGE + '/release_manifest.json', 'w') as stream:
                stream.write(json.dumps(candidate_release, indent=2))
            print('Staged current dependencies plus verified virtual candidate', flush=True)
            tests = checked(client, 'cd ' + STAGE + ' && timeout 45s env PYTHONDONTWRITEBYTECODE=1 '
                            '/usr/local/share/pynq-venv/bin/python3 -m unittest '
                            'test_mi_formal_entry test_mi_cued test_mi_virtual')
            (OUT / 'live_stage_tests.log').write_text(tests, encoding='utf-8')
            # Recheck recorder immediately before the only service interruption.
            if read_json(sftp, '/run/guardianloop/recording_status.json').get('state') == 'recording':
                raise RuntimeError('A recording started during staging')
            checked(client, 'systemctl stop ' + UNITS, sudo=True)
            changed = True
            checked(client, 'install -d -m 755 /run/guardianloop-mi-live '
                            '/run/systemd/system/guardianloop-cyton.service.d '
                            '/run/systemd/system/guardianloop-web.service.d', sudo=True)
            checked(client, 'install -m 644 ' + STAGE + '/config.json '
                            '/run/guardianloop-mi-live/config.json', sudo=True)
            for name, destination in OVERRIDES.items():
                checked(client, 'install -m 644 ' + STAGE + '/' + name + ' '
                        + shlex.quote(destination), sudo=True)
            checked(client, 'systemctl daemon-reload', sudo=True)
            checked(client, 'systemctl start ' + UNITS, sudo=True)
            status = None
            probe = ("import json; from urllib.request import urlopen; "
                     "print(json.dumps(json.load(urlopen('http://127.0.0.1:9102/api/mi-cue',timeout=2))))")
            for attempt in range(25):
                time.sleep(1)
                try:
                    status = json.loads(checked(client, 'python3 -c ' + shlex.quote(probe)))
                except RuntimeError:
                    if attempt == 24:
                        raise
                    continue
                if status.get('received_samples', 0) >= 500:
                    break
            if (not status or status.get('source') != 'live' or not status.get('enabled')
                    or status.get('channels') != release['channels']
                    or status.get('control_enabled') is not False
                    or status.get('production_eligible') is not False
                    or status.get('received_samples', 0) < 500):
                raise RuntimeError('Candidate did not establish a real, non-actuating input')
            after = protect(client, sftp, release)
            if after != before:
                raise RuntimeError('Protected formal files/config or boot identity changed')
            evidence = dict(before=before, after=after, protected_unchanged=True,
                            files=files, stage=STAGE, runtime_overrides=OVERRIDES,
                            live_snapshot=status, source='live', hardware_control=False,
                            model_promoted=False, pl_changed=False, boot_changed=False,
                            services=checked(client, 'systemctl is-active ' + UNITS),
                            rollback='python eeg_apps_z15/deploy_mi_live_virtual.py --restore')
            (OUT / 'DEPLOYMENT.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2),
                                                 encoding='utf-8')
            print(json.dumps({key: evidence[key] for key in ('stage','services','protected_unchanged',
                              'source','hardware_control','model_promoted','pl_changed','live_snapshot')},
                             ensure_ascii=False), flush=True)
    except BaseException:
        if changed:
            print('Withdrawing temporary overrides and restarting original services', flush=True)
            restore(client)
        raise
    finally:
        client.close()


if __name__ == '__main__':
    main()

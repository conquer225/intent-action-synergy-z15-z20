"""Board-local, web-only transaction. No acquisition or PL operations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.request import urlopen

APP = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
TARGETS = ('guardianloop_web.py', 'mobile.html', 'mobile.js', 'release_manifest.json')
STARTUP = Path('/run/guardianloop-startup/status.json')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def get_json(route):
    with urlopen('http://127.0.0.1:9102'+route, timeout=4) as response:
        return json.load(response)


def service(name):
    output = subprocess.check_output(['systemctl', 'show', name, '--property=MainPID',
        '--property=ActiveState', '--property=NRestarts'], text=True)
    return dict(line.split('=', 1) for line in output.splitlines())


def audit(paths):
    manifest = json.loads((APP/'release_manifest.json').read_text())
    status = get_json('/api/status')
    sessions = {}
    for route in ('/api/mi-cue', '/api/ssvep-cue', '/api/ssvep-free', '/api/recording'):
        value = get_json(route)
        if route == '/api/recording':
            value = value.get('recording', {})
        sessions[route] = {key:value.get(key) for key in ('state','id','trial_id')}
    hashes = {path:digest(path) for path in paths}
    return dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        manifest=manifest, hashes=hashes, startup_hash=digest(STARTUP),
        startup=status['system']['startup'], cyton=service('guardianloop-cyton.service'),
        web=service('guardianloop-web.service'), sessions=sessions,
        existing_mobile={name:(digest(APP/name) if (APP/name).exists() else None)
                         for name in ('mobile.html','mobile.js')})


def idle(snapshot):
    for route, value in snapshot['sessions'].items():
        if value.get('state') in ('active','awaiting_presentation','recording','starting','preparing'):
            raise RuntimeError('Active session: '+route)


def restart_web():
    subprocess.run(['systemctl','restart','guardianloop-web.service'], check=True, timeout=20)


def run(stage):
    stage = stage.resolve()
    if stage.parent != Path('/home/xilinx') or not stage.name.startswith('mobile-web-'):
        raise ValueError('Unexpected transaction directory')
    expected = json.loads((stage/'expected.json').read_text())
    result = dict(passed=False, phase='preflight', stage=str(stage))
    installed = []
    originals = {}
    original_info = {}
    try:
        before = audit(expected['guard'])
        idle(before)
        if before != expected['before']:
            # Session IDs may expire while staging; compare invariant fields, then recheck idle.
            for key in ('boot_id','hashes','startup_hash','cyton','web','existing_mobile'):
                if before[key] != expected['before'][key]:
                    raise RuntimeError('Preflight changed: '+key)
        if before['hashes'] != expected['guard']:
            raise RuntimeError('Formal files do not match approved baseline')
        if before['cyton']['ActiveState'] != 'active' or before['web']['ActiveState'] != 'active':
            raise RuntimeError('Expected services are not active')
        compile((stage/'new/guardianloop_web.py').read_text(), 'guardianloop_web.py', 'exec')
        for name in TARGETS:
            if digest(stage/'new'/name) != expected['new_hashes'][name]:
                raise RuntimeError('Staged hash mismatch: '+name)
        backup = stage/'backup'
        backup.mkdir()
        for name in TARGETS:
            target = APP/name
            originals[name] = digest(target) if target.exists() else None
            if target.exists():
                info = target.stat()
                original_info[name] = (info.st_uid, info.st_gid, info.st_mode & 0o777)
                shutil.copy2(target, backup/name)
        (stage/'originals.json').write_text(json.dumps(originals, indent=2))
        result['phase'] = 'installing'
        for name in TARGETS:
            target = APP/name
            temporary = APP/('.'+name+'.'+stage.name)
            shutil.copy2(stage/'new'/name, temporary)
            if target.exists():
                info = target.stat()
            else:
                info = (APP/'guardianloop_web.py').stat()
            os.chown(temporary, info.st_uid, info.st_gid)
            os.chmod(temporary, info.st_mode & 0o777)
            os.replace(temporary, target)
            installed.append(name)
        restart_web()
        result['phase'] = 'verifying'
        for attempt in range(12):
            try:
                after = audit(expected['guard'])
                break
            except OSError:
                if attempt == 11:
                    raise
                time.sleep(.5)
        guard_after = dict(after['hashes'])
        for name in ('guardianloop_web.py','release_manifest.json'):
            guard_after[str(APP/name)] = expected['guard'][str(APP/name)]
        if guard_after != expected['guard']:
            raise RuntimeError('Protected files changed')
        for key in ('boot_id','startup_hash','cyton'):
            if after[key] != before[key]:
                raise RuntimeError('Protected runtime changed: '+key)
        if after['web']['ActiveState'] != 'active' or after['web']['MainPID'] == before['web']['MainPID']:
            raise RuntimeError('Web restart not confirmed')
        routes = {}
        for route in ('/','/mobile','/mobile/','/mobile.js','/mi-cued','/ssvep-cued','/ssvep-free',
                      '/api/status','/api/seed-shadow','/api/ssvep-shadow','/api/mi-cue','/healthz'):
            with urlopen('http://127.0.0.1:9102'+route, timeout=4) as response:
                body = response.read()
                routes[route] = dict(status=response.status, bytes=len(body),
                    content_type=response.headers.get('Content-Type'),
                    cache_control=response.headers.get('Cache-Control'))
                if route in ('/mobile','/mobile/') and '手机监控'.encode() not in body:
                    raise RuntimeError('Wrong mobile page')
                if route == '/mobile.js' and hashlib.sha256(body).hexdigest() != expected['new_hashes']['mobile.js']:
                    raise RuntimeError('Wrong JavaScript response')
                if route == '/' and b'/mobile' not in body:
                    raise RuntimeError('Main page link missing')
                if route.startswith('/mobile') and response.headers.get('Cache-Control') != 'no-store':
                    raise RuntimeError('Mobile page caching enabled')
        installed_hashes = {name:digest(APP/name) for name in TARGETS}
        if installed_hashes != expected['new_hashes']:
            raise RuntimeError('Installed artifact mismatch')
        if after['startup'].get('installed_release_id') != expected['release_id']:
            raise RuntimeError('Updated release not visible')
        result.update(passed=True, phase='verified', before=before, after=after,
            routes=routes, installed_hashes=installed_hashes, backup=str(backup))
    except Exception as error:
        result['error'] = type(error).__name__+': '+str(error)
        if installed:
            try:
                for name in reversed(installed):
                    target = APP/name
                    if originals[name] is None:
                        # Retain newly introduced files in the transaction, not destructive deletion.
                        os.replace(target, stage/('withdrawn-'+name))
                    else:
                        temporary = APP/('.rollback-'+name+'.'+stage.name)
                        shutil.copy2(stage/'backup'/name, temporary)
                        uid, gid, mode = original_info[name]
                        os.chown(temporary, uid, gid)
                        os.chmod(temporary, mode)
                        os.replace(temporary, target)
                restart_web()
                result['phase'] = 'rolled_back'
                result['rollback_hashes'] = {name:(digest(APP/name) if (APP/name).exists() else None) for name in TARGETS}
            except Exception as rollback_error:
                result['rollback_error'] = str(rollback_error)
                result['phase'] = 'rollback_requires_attention'
    (stage/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(dict(passed=result['passed'], phase=result['phase'], error=result.get('error'))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    run(parser.parse_args().stage)

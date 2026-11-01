"""Install or undo the production startup service; preserve boot images and models."""

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil

from run_soak_stage import ROOT, PROD, connect, command
from deploy_ssvep_rail_coalesce import sudo


SOURCE = ROOT / 'pynq_guardianloop'
OUT = ROOT / 'eeg_apps_z15/output/startup_deployment_20261001'
LEDGER = OUT / 'deployment.json'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'
OLD_WEB = '6e2a7fb370300a4482fba83ab7f708066cf5069f0d2833c7a86e18b416a233fb'
BIT_HASH = 'c39b891704471a712fb7be3591841af1dd6791387957b873b11450c99eca41ca'
HWH_HASH = '2ab7ffa36398be4eee20d90512c7f1c6d29a7066c9d1bf0683a3bcad2501f92b'
RUNTIME_FILES = (
    'cyton_guardianloop.py', 'guardianloop_pynq.py', 'cyton_sqi.py', 'pl_causal_filter.py',
    'cyton_covariance.py', 'cyton_trial_recorder.py', 'cyton_fatigue.py', 'seed_shadow.py',
    'seed_quality_runtime.py', 'seed_shadow_policy.py', 'seed_gate_policy.py', 'seed_replay_check.py',
    'ssvep_shadow.py', 'ssvep_stream.py', 'ssvep_core.py', 'guardianloop_web.py', 'ssvep_cued.py',
    'gameemo_covariance_svm.npz', 'cyton_fatigue_overlap4.json', 'seed_shadow_weights.npz',
    'ssvep_causal_protocol.json', 'ssvep_candidate_sos.npy',
    'guardianloop_pynq.bit', 'guardianloop_pynq.hwh',
)
CONFIGS = {
    'guardianloop-startup.service': '/etc/systemd/system/guardianloop-startup.service',
    'guardianloop-cyton-startup.conf': '/etc/systemd/system/guardianloop-cyton.service.d/20-startup.conf',
    'guardianloop-web-startup.conf': '/etc/systemd/system/guardianloop-web.service.d/20-startup.conf',
}


def digest(sftp, path):
    with sftp.open(path, 'rb') as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def save(value):
    LEDGER.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def verify(client, ledger, filename='postflight.json'):
    startup = json.loads(command(client, 'cat /run/guardianloop-startup/status.json'))
    current_boot = command(client, 'cat /proc/sys/kernel/random/boot_id').strip()
    if startup['state'] != 'ready' or startup['boot_id'] != current_boot:
        raise RuntimeError('Startup self-test is not ready for the current boot')
    if startup['release_id'] != ledger['release_id']:
        raise RuntimeError('Startup report belongs to another release')
    with client.open_sftp() as sftp:
        current = {name: digest(sftp, PROD + '/' + name) for name in ledger['release_files']}
        if current != ledger['release_files']:
            raise RuntimeError('Installed release changed after deployment')
        for name, path in CONFIGS.items():
            if digest(sftp, path) != ledger['config_hashes'][name]:
                raise RuntimeError('Startup unit changed: ' + name)
    system = json.loads(command(client, 'curl --max-time 5 -fsS http://127.0.0.1:9102/api/status'))
    cue = json.loads(command(client, 'curl --max-time 5 -fsS http://127.0.0.1:9102/api/ssvep-cue'))
    if system['system']['startup']['state'] != 'ready' or cue.get('control_enabled') is not False:
        raise RuntimeError('Web startup or cue endpoint failed verification')
    services = command(client, 'systemctl show guardianloop-startup guardianloop-web guardianloop-cyton '
                       '-p Id -p ActiveState -p SubState -p MainPID -p Requires -p After')
    for prop in ('Requires', 'After'):
        value = command(client, 'systemctl show guardianloop-cyton.service --value -p ' + prop)
        if 'guardianloop-startup.service' not in value.split():
            raise RuntimeError('Acquisition startup dependency is missing: ' + prop)
    command(client, 'systemctl is-active --quiet guardianloop-startup.service guardianloop-web.service')
    command(client, 'systemctl is-enabled --quiet guardianloop-startup.service guardianloop-cyton.service guardianloop-web.service')
    checks = {'startup': startup, 'boot_id': current_boot, 'system': system['system'],
              'cue_state': cue['state'], 'services': services, 'installed_hashes': current,
              'boot_hashes': command(client, 'sha256sum /boot/BOOT.BIN /boot/image.ub /boot/boot.scr')}
    if checks['boot_hashes'] != ledger['boot_hashes']:
        raise RuntimeError('Boot image files changed')
    (OUT / filename).write_text(json.dumps(checks, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return checks


def restore(client, ledger):
    present_apps = []
    present_configs = []
    with client.open_sftp() as sftp:
        if digest(sftp, ledger['stage'] + '/guardianloop_web.py.original') != OLD_WEB:
            raise RuntimeError('Original web backup failed checksum validation')
        for name in ('guardianloop_web.py', 'guardianloop_startup.py', 'release_manifest.json'):
            try:
                current = digest(sftp, PROD + '/' + name)
            except FileNotFoundError:
                continue
            if name == 'guardianloop_web.py' and current == OLD_WEB:
                continue
            if current != ledger['installed_files'][name]:
                raise RuntimeError('Another update changed ' + name + '; refused rollback overwrite')
            present_apps.append(name)
        for name, path in CONFIGS.items():
            try:
                current = digest(sftp, path)
            except FileNotFoundError:
                continue
            if current != ledger['config_hashes'][name]:
                raise RuntimeError('Another update changed ' + path)
            present_configs.append(path)
    sudo(client, 'systemctl stop guardianloop-cyton.service guardianloop-web.service')
    if CONFIGS['guardianloop-startup.service'] in present_configs:
        sudo(client, 'systemctl disable --now guardianloop-startup.service')
    with client.open_sftp() as sftp:
        for name in ('guardianloop_startup.py', 'release_manifest.json'):
            if name in present_apps:
                sftp.remove(PROD + '/' + name)
        if 'guardianloop_web.py' in present_apps:
            command(client, 'cp -p ' + shlex.quote(ledger['stage'] + '/guardianloop_web.py.original')
                    + ' ' + shlex.quote(PROD + '/guardianloop_web.py.rollback'))
            sftp.posix_rename(PROD + '/guardianloop_web.py.rollback', PROD + '/guardianloop_web.py')
    # Exact files added by this deployment; original units are never overwritten.
    if present_configs:
        sudo(client, 'rm -- ' + ' '.join(shlex.quote(path) for path in present_configs))
    sudo(client, 'systemctl daemon-reload')
    sudo(client, 'systemctl start guardianloop-web.service guardianloop-cyton.service')
    ledger['phase'] = 'rolled_back'
    save(ledger)


def install():
    if LEDGER.exists():
        raise RuntimeError('Deployment ledger already exists; inspect it before another install')
    OUT.mkdir(parents=True, exist_ok=True)
    snapshot = OUT / 'original_runtime'
    package = OUT / 'package'
    runtime = package / 'runtime'
    snapshot.mkdir(); runtime.mkdir(parents=True)
    client = connect()
    ledger = None
    switched = False
    stopped = False
    try:
        with client.open_sftp() as sftp:
            before = {name: digest(sftp, PROD + '/' + name) for name in RUNTIME_FILES}
            if before['guardianloop_web.py'] != OLD_WEB or before['guardianloop_pynq.bit'] != BIT_HASH or before['guardianloop_pynq.hwh'] != HWH_HASH:
                raise RuntimeError('Formal web or PL pair changed; refused deployment')
            for name in RUNTIME_FILES:
                sftp.get(PROD + '/' + name, str(snapshot / name))
                if hashlib.sha256((snapshot / name).read_bytes()).hexdigest() != before[name]:
                    raise RuntimeError('Recovery snapshot checksum failed: ' + name)
                shutil.copy2(snapshot / name, runtime / name)
        for target in (*CONFIGS.values(), PROD + '/guardianloop_startup.py', PROD + '/release_manifest.json'):
            command(client, 'test ! -e ' + shlex.quote(target))
        command(client, "test ! -e /dev/guardianloop_dma_keeper && "
                "test ! -e /proc/device-tree/amba/dma-owner@40410000 && "
                "! grep -q '^gldma_owner ' /proc/modules")
        for name in ('guardianloop_web.py', 'guardianloop_startup.py'):
            shutil.copy2(SOURCE / name, runtime / name)
        hashes = {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
                  for name in (*RUNTIME_FILES, 'guardianloop_startup.py')}
        manifest = {'release_id': 'guardianloop-fixed-cap-20261001',
                    'channels': ['F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2'], 'files': hashes}
        (runtime / 'release_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        stage = PROD + '/startup-release-20261001'
        command(client, 'mkdir ' + shlex.quote(stage))
        configs = package / 'systemd'; configs.mkdir()
        for name in CONFIGS:
            shutil.copy2(SOURCE / name, configs / name)
        installed = {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
                     for name in ('guardianloop_web.py', 'guardianloop_startup.py', 'release_manifest.json')}
        ledger = {'phase': 'prepared', 'stage': stage, 'release_id': manifest['release_id'],
                  'production_before': before, 'release_files': hashes, 'installed_files': installed,
                  'config_hashes': {name: hashlib.sha256((configs / name).read_bytes()).hexdigest() for name in CONFIGS},
                  'boot_hashes': command(client, 'sha256sum /boot/BOOT.BIN /boot/image.ub /boot/boot.scr'),
                  'boot_id_before': command(client, 'cat /proc/sys/kernel/random/boot_id').strip(),
                  'units_before': command(client, 'systemctl cat guardianloop-cyton.service guardianloop-web.service')}
        save(ledger)
        with client.open_sftp() as sftp:
            sftp.put(str(snapshot / 'guardianloop_web.py'), stage + '/guardianloop_web.py.original')
            for name in installed:
                sftp.put(str(runtime / name), stage + '/' + name)
                if digest(sftp, stage + '/' + name) != installed[name]:
                    raise RuntimeError('Candidate upload checksum failed: ' + name)
            for name in CONFIGS:
                sftp.put(str(configs / name), stage + '/' + name)
                if digest(sftp, stage + '/' + name) != ledger['config_hashes'][name]:
                    raise RuntimeError('Unit upload checksum failed: ' + name)
        command(client, 'env PYTHONPATH=' + shlex.quote(PROD) + ' ' + PYTHON + ' -c '
                + shlex.quote('import ast; from pathlib import Path; '
                              f'[ast.parse((Path({stage!r})/n).read_text()) for n in '
                              "('guardianloop_web.py','guardianloop_startup.py')]"))
        sudo(client, 'systemctl stop guardianloop-cyton.service guardianloop-web.service')
        stopped = True
        switched = True
        with client.open_sftp() as sftp:
            for name in installed:
                command(client, 'cp -p ' + shlex.quote(stage + '/' + name) + ' ' + shlex.quote(PROD + '/' + name + '.install'))
                sftp.posix_rename(PROD + '/' + name + '.install', PROD + '/' + name)
        for name, target in CONFIGS.items():
            sudo(client, 'install -D -m 644 ' + shlex.quote(stage + '/' + name) + ' ' + shlex.quote(target))
        ledger['phase'] = 'installed_pending_checks'; save(ledger)
        sudo(client, 'systemctl daemon-reload')
        sudo(client, 'systemd-analyze verify /etc/systemd/system/guardianloop-startup.service '
             '/etc/systemd/system/guardianloop-cyton.service /etc/systemd/system/guardianloop-web.service')
        sudo(client, 'systemctl enable guardianloop-startup.service')
        sudo(client, 'systemctl start guardianloop-startup.service')
        sudo(client, 'systemctl start guardianloop-web.service guardianloop-cyton.service')
        checks = verify(client, ledger)
        ledger['phase'] = 'installed_verified'; save(ledger)
        print('STARTUP_DEPLOYED', json.dumps(checks['startup'], ensure_ascii=False), flush=True)
    except Exception:
        if switched and ledger is not None:
            restore(client, ledger)
        elif stopped:
            sudo(client, 'systemctl start guardianloop-web.service guardianloop-cyton.service')
        raise
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'verify', 'rollback'))
    args = parser.parse_args()
    if args.action == 'install':
        install(); return
    ledger = json.loads(LEDGER.read_text(encoding='utf-8'))
    client = connect()
    try:
        if args.action == 'rollback':
            restore(client, ledger)
        else:
            result = verify(client, ledger, 'reboot_postflight.json')
            print('STARTUP_VERIFIED', result['boot_id'], flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    main()

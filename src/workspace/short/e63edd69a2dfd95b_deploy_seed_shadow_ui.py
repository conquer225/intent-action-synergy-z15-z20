"""Deploy only the reviewed SEED shadow presentation, without restarting acquisition."""
import hashlib
import json
import os
import time
from pathlib import Path

import paramiko

from .deploy_seed_shadow import run


ROOT = Path(__file__).resolve().parents[1]
REMOTE = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
PREVIOUS_WEB_SHA256 = '302191ae269363ea1fb38844e479111bd56c98a6e541f089d9b0f10715c03559'
PROTECTED = ('cyton_guardianloop.py', 'seed_shadow.py', 'seed_shadow_weights.npz',
             'gameemo_covariance_svm.npz', 'cyton_fatigue_overlap4.json',
             'guardianloop_pynq.bit', 'guardianloop_pynq.hwh')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restart_web(client, password):
    stdin, stdout, stderr = client.exec_command(
        'sudo -S systemctl restart guardianloop-web.service', timeout=30)
    stdin.write(password + '\n')
    stdin.flush()
    stdin.channel.shutdown_write()
    output = stdout.read().decode() + stderr.read().decode()
    if stdout.channel.recv_exit_status():
        raise RuntimeError('Web service restart failed: ' + output)


def main():
    stamp = time.strftime('%Y%m%d-%H%M%S')
    out = ROOT / ('eeg_apps_z15/output/seed_shadow_ui_' + stamp)
    if out.exists():
        raise FileExistsError('Preserve the existing deployment ledger: ' + str(out))
    out.mkdir(parents=True)
    source = ROOT / 'pynq_guardianloop/guardianloop_web.py'
    tests = ROOT / 'pynq_guardianloop/test_seed_shadow_web.py'
    stage = '/home/xilinx/jupyter_notebooks/seed_shadow_ui_stage_' + stamp
    backup = REMOTE + '/backup-seed-shadow-ui-' + stamp
    ledger = {'phase': 'starting', 'stage': stage, 'backup': backup,
              'web_sha256': digest(source), 'test_sha256': digest(tests)}

    def save():
        (out / 'deployment.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding='utf-8')

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    password = os.environ.get('GL_PYNQ_PASSWORD', 'xilinx')
    client.connect('192.168.2.99', username='xilinx', password=password, timeout=8)
    changed = False
    try:
        current = run(client, 'sha256sum ' + REMOTE + '/guardianloop_web.py').split()[0]
        ledger['previous_web_sha256'] = current
        if current != PREVIOUS_WEB_SHA256:
            raise RuntimeError('Board web file changed since last verified deployment; not overwriting')
        check = 'sha256sum ' + ' '.join(REMOTE + '/' + name for name in PROTECTED)
        ledger['protected_before'] = run(client, check)
        save()
        run(client, 'mkdir ' + stage)
        with client.open_sftp() as sftp:
            sftp.put(str(source), stage + '/guardianloop_web.py')
            sftp.put(str(tests), stage + '/test_seed_shadow_web.py')
        for name, expected in [('guardianloop_web.py', ledger['web_sha256']),
                               ('test_seed_shadow_web.py', ledger['test_sha256'])]:
            if run(client, 'sha256sum ' + stage + '/' + name).split()[0] != expected:
                raise RuntimeError('Staged file hash mismatch: ' + name)
        env = ('cd ' + stage + '; PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=' + stage + ':' + REMOTE +
               ' /usr/local/share/pynq-venv/bin/python3 -m unittest test_seed_shadow_web 2>&1')
        ledger['board_tests'] = run(client, env, timeout=90)
        ledger['phase'] = 'verified'
        save()
        run(client, 'mkdir ' + backup)
        run(client, 'cp -p ' + REMOTE + '/guardianloop_web.py ' + backup + '/guardianloop_web.py')
        with client.open_sftp() as sftp:
            temporary = REMOTE + '/guardianloop_web.py.ui-new'
            sftp.put(str(source), temporary)
            if run(client, 'sha256sum ' + temporary).split()[0] != ledger['web_sha256']:
                raise RuntimeError('Uploaded file hash mismatch')
            sftp.posix_rename(temporary, REMOTE + '/guardianloop_web.py')
        changed = True
        restart_web(client, password)
        time.sleep(2)
        ledger['web_service'] = run(client, 'systemctl is-active guardianloop-web.service').strip()
        ledger['cyton_service'] = run(client, 'systemctl is-active guardianloop-cyton.service').strip()
        if ledger['web_service'] != 'active' or ledger['cyton_service'] != 'active':
            raise RuntimeError('One or more services inactive after web-only deployment')
        page = run(client, 'curl -fsS http://127.0.0.1:9102/')
        for marker in ('SEED 正／中／负影片条件 · 八通道候选',
                       '不是当前佩戴者的准确率', '历史离线回放（非当前佩戴者）'):
            if marker not in page:
                raise RuntimeError('Live page missing expected marker: ' + marker)
        shadow = json.loads(run(client, 'curl -fsS http://127.0.0.1:9102/api/seed-shadow'))
        ledger['live_api'] = {'stale': shadow['stale'],
                              'state': shadow['live'].get('state'),
                              'valid': shadow['live'].get('valid'),
                              'policy_version': shadow['live'].get('policy_version'),
                              'replay_source': shadow['replay'].get('source')}
        ledger['protected_after'] = run(client, check)
        if ledger['protected_after'] != ledger['protected_before']:
            raise RuntimeError('Protected model/acquisition files changed')
        ledger['phase'] = 'deployed'
        save()
        print('SEED_SHADOW_UI_DEPLOYED ' + str(out / 'deployment.json'), flush=True)
    except Exception:
        if changed:
            run(client, 'cp -p ' + backup + '/guardianloop_web.py ' + REMOTE + '/guardianloop_web.py')
            restart_web(client, password)
            ledger['phase'] = 'rolled_back'
        else:
            ledger['phase'] = 'not_installed'
        save()
        raise
    finally:
        client.close()


if __name__ == '__main__':
    main()

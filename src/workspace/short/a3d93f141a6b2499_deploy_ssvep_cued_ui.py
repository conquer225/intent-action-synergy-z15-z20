"""Deploy only the cued-SSVEP web layer, with a board-local rollback copy.

Does not change acquisition, PL, boot files, or any model weights.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.request import urlopen

import paramiko


HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent / 'pynq_guardianloop'
REMOTE = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
EXPECTED_WEB_SHA256 = {
    '5d3513d28563eef44bfb315ef70ed4dfcbd5bc073c6ccec8cebeb46092a25dff',
    'adbe77aecc98b682600797745c1d63ad1f1410fd2b5fc5e7567b6bfba238881e',
    'a42dc44a6e0c2372465f8b7afeffc1268e0b77ac9501ae8e32dd423abd14c35a',
    '29931b2382b10efc69635ad20590a5b0c7779f6b930d9dc9b8cfd91ab3646f68',
    '7fcc94aab18ba20bf773c462e68184e596dfc08c795683fdf36affca00416c7a',
    '6e6fbb181e7d1a8b4dd564e5ed3c81505ff13c28651416a462987a41cbfaeab5',
    '6e2a7fb370300a4482fba83ab7f708066cf5069f0d2833c7a86e18b416a233fb',
}
EXPECTED_MODULE_SHA256 = {
    'cc6dcb718be9e838efe1daa71312b8fe83662e78ef7b9634b6987c294b1dd792',
    '89965e74756f728bf3f2d7fa585d0a92d99e952ca0dcc7e64229656d9e16e79a',
    'a3e4faf973303a637ef1c8434784962d5127caaf8f1f8b14afbc1a8a4f73b342',
}


def run(client, command, password=None):
    stdin, stdout, stderr = client.exec_command(command, timeout=20)
    if password is not None:
        stdin.write(password+'\n')
        stdin.flush()
    code = stdout.channel.recv_exit_status()
    output = stdout.read().decode('utf-8', 'replace') + stderr.read().decode('utf-8', 'replace')
    if code:
        raise RuntimeError(f'{command}: {output}')
    return output.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.2.99')
    parser.add_argument('--user', default='xilinx')
    parser.add_argument('--password', default='xilinx')
    args = parser.parse_args()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.user, password=args.password, timeout=8)
    web_changed = module_changed = False
    stamp = time.strftime('%Y%m%d-%H%M%S')
    backup = f'{REMOTE}/guardianloop_web.py.before-ssvep-cued-{stamp}'
    module_backup = f'{REMOTE}/ssvep_cued.py.before-ssvep-cued-{stamp}'
    web = f'{REMOTE}/guardianloop_web.py'
    module = f'{REMOTE}/ssvep_cued.py'
    try:
        run(client, 'sudo -S -v', args.password)
        with client.open_sftp() as sftp:
            old = sftp.open(web, 'rb').read()
            digest = hashlib.sha256(old).hexdigest()
            if digest not in EXPECTED_WEB_SHA256:
                raise RuntimeError(f'Board web file changed; refused overwrite: {digest}')
            old_module = sftp.open(module, 'rb').read()
            current_module = hashlib.sha256(old_module).hexdigest()
            if current_module not in EXPECTED_MODULE_SHA256:
                raise RuntimeError(f'Board cue module changed; refused overwrite: {current_module}')
            for target in (backup, module_backup):
                try:
                    sftp.stat(target)
                    raise RuntimeError(f'Rollback file already exists: {target}')
                except FileNotFoundError:
                    pass
            for name in ('ssvep_cued.py', 'guardianloop_web.py'):
                source = LOCAL/name
                if not source.is_file():
                    raise FileNotFoundError(source)
                sftp.put(str(source), f'{REMOTE}/{name}.cued-candidate')
            run(client, 'python3 -c "import ast; '
                f'[ast.parse(open(p, encoding=\'utf-8\').read()) for p in '
                f'({REMOTE!r}+\'/ssvep_cued.py.cued-candidate\', '
                f'{REMOTE!r}+\'/guardianloop_web.py.cued-candidate\')]"')
            with sftp.open(backup, 'wb') as handle:
                handle.write(old)
            with sftp.open(module_backup, 'wb') as handle:
                handle.write(old_module)
            sftp.posix_rename(f'{module}.cued-candidate', module)
            module_changed = True
            sftp.posix_rename(f'{web}.cued-candidate', web)
            web_changed = True
        run(client, f'cd {REMOTE} && python3 -c "from guardianloop_web import make_handler; print(\'IMPORT_OK\')"')
        run(client, 'sudo -S systemctl restart guardianloop-web.service', args.password)
        for _ in range(10):
            try:
                with urlopen(f'http://{args.host}:9102/ssvep-cued', timeout=3) as response:
                    page_ok = response.status == 200 and '有提示 SSVEP'.encode() in response.read()
                with urlopen(f'http://{args.host}:9102/api/ssvep-cue', timeout=3) as response:
                    cue = json.load(response)
                with urlopen(f'http://{args.host}:9102/api/status', timeout=3) as response:
                    status_ok = response.status == 200
                if page_ok and cue.get('state') == 'idle' and status_ok:
                    print(json.dumps({'deployed': True, 'page': f'http://{args.host}:9102/ssvep-cued',
                                      'cue_state': cue['state'],
                                      'rollback_web': backup,
                                      'rollback_module': module_backup}, ensure_ascii=False))
                    return
            except (OSError, ValueError):
                pass
            time.sleep(1)
        raise RuntimeError('HTTP postflight failed')
    except Exception:
        if web_changed or module_changed:
            with client.open_sftp() as sftp:
                if web_changed:
                    sftp.posix_rename(backup, web)
                if module_changed:
                    sftp.posix_rename(module_backup, module)
            run(client, 'sudo -S systemctl restart guardianloop-web.service', args.password)
            print('Web layer restored from board-local backups')
        raise
    finally:
        client.close()


if __name__ == '__main__':
    main()

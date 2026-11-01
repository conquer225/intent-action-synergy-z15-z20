"""Read-only Z15 snapshot and local recovery copies. Never writes to the board."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import shlex

import paramiko


REMOTE = r'''
import base64, glob, hashlib, json, os, subprocess
from pathlib import Path
def command(args):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, timeout=15)
    return {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
result = {'commands': {}, 'device_tree': {}, 'platform_resources': {}, 'files': []}
for key, args in {
    'kernel': ['uname', '-a'], 'services': ['systemctl', 'show',
        'guardianloop-cyton.service', 'guardianloop-web.service',
        '-p', 'Id', '-p', 'ActiveState', '-p', 'SubState', '-p', 'ExecStart',
        '-p', 'FragmentPath', '-p', 'Restart', '-p', 'NRestarts'],
    'network': ['ip', '-j', 'addr'], 'mounts': ['findmnt', '-J'],
    'units': ['systemctl', 'list-unit-files', 'guardianloop*', '--no-pager'],
    'recent_cyton_journal': ['journalctl', '-u', 'guardianloop-cyton.service', '-n', '45', '--no-pager']
}.items(): result['commands'][key] = command(args)
for name in ('iomem', 'cmdline', 'modules', 'meminfo', 'loadavg'):
    result['commands'][name] = {'stdout': Path('/proc', name).read_text()}
for root, dirs, files in os.walk('/sys/firmware/devicetree/base'):
    for name in files:
        p = Path(root, name)
        result['device_tree'][str(p.relative_to('/sys/firmware/devicetree/base'))] = base64.b64encode(p.read_bytes()).decode()
fdt = Path('/sys/firmware/fdt')
result['boot_fdt'] = base64.b64encode(fdt.read_bytes()).decode() if fdt.exists() else None
for p in Path('/sys/bus/platform/devices').glob('*'):
    resource = p / 'resource'
    result['platform_resources'][p.name] = {
        'resource': resource.read_text() if resource.exists() else None,
        'driver': str((p / 'driver').resolve()) if (p / 'driver').exists() else None,
        'of_node': str((p / 'of_node').resolve()) if (p / 'of_node').exists() else None}
paths = list(Path('/boot').glob('*'))
runtime = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
paths += [p for p in runtime.glob('*') if p.suffix in ('.py', '.json', '.npz', '.hwh', '.bit')]
paths += list(Path('/etc/systemd/system').glob('guardianloop*'))
paths += [Path('/etc/hostapd/hostapd.conf'), Path('/etc/dnsmasq.conf'),
          Path('/etc/network/interfaces'), Path('/etc/modules')]
for p in paths:
    if p.is_file():
        data = p.read_bytes()
        result['files'].append({'path': str(p), 'size': len(data),
                               'sha256': hashlib.sha256(data).hexdigest()})
print(json.dumps(result))
'''


class PinnedHostKey(paramiko.MissingHostKeyPolicy):
    def __init__(self, expected):
        self.expected = expected

    def missing_host_key(self, client, hostname, key):
        if hashlib.sha256(key.asbytes()).hexdigest() != self.expected:
            raise paramiko.SSHException('Z15 host key differs from pinned identity')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.2.99')
    parser.add_argument('--user', default='xilinx')
    parser.add_argument('--host-key-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true',
                        help='Compare protected board files against an existing local snapshot')
    args = parser.parse_args()
    if not args.verify_only:
        args.output.mkdir(parents=True, exist_ok=False)
    password = os.environ.get('GL_BOARD_PASSWORD') or getpass.getpass('Z15 password: ')
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(PinnedHostKey(args.host_key_sha256))
    try:
        client.connect(args.host, username=args.user, password=password,
                       timeout=8, auth_timeout=8, banner_timeout=8)
        actual_key = hashlib.sha256(client.get_transport().get_remote_server_key().asbytes()).hexdigest()
        if actual_key != args.host_key_sha256:
            raise paramiko.SSHException('Z15 host key differs from pinned identity')
        stdin, stdout, stderr = client.exec_command(
            'sudo -S -p "" /usr/bin/python3 -c ' + shlex.quote(REMOTE), timeout=45)
        stdin.write(password + '\n')
        stdin.flush()
        stdin.channel.shutdown_write()
        payload = stdout.read()
        errors = stderr.read().decode()
        if stdout.channel.recv_exit_status():
            raise RuntimeError('Read-only board collector failed: ' + errors)
        snapshot = json.loads(payload)
        snapshot['host_key_sha256'] = actual_key
        snapshot['collected_at_host_utc'] = datetime.now(timezone.utc).isoformat()
        snapshot['scope'] = 'read-only; no MMIO, serial, insmod, reset, service or board file changes'
        if args.verify_only:
            baseline = json.loads((args.output / 'board_snapshot.json').read_text())
            old = {item['path']: item['sha256'] for item in baseline['files']}
            current = {item['path']: item['sha256'] for item in snapshot['files']}
            changed = [path for path, digest in old.items() if current.get(path) != digest]
            result = {'status': 'PROTECTED_FILES_UNCHANGED' if not changed else 'FILES_CHANGED_REVIEW_REQUIRED',
                      'checked_files': len(old), 'changed': changed,
                      'live_dt_properties_unchanged': baseline['device_tree'] == snapshot['device_tree'],
                      'observations': snapshot}
            (args.output / 'postcheck.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps({key: value for key, value in result.items() if key != 'observations'}))
            if changed:
                raise RuntimeError('Protected board files changed during the preparation')
            return
        snapshot['backup_verified'] = []
        with client.open_sftp() as sftp:
            for item in snapshot['files']:
                target = args.output / 'recovery' / item['path'].lstrip('/')
                target.parent.mkdir(parents=True, exist_ok=True)
                sftp.get(item['path'], str(target))
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                if digest != item['sha256']:
                    raise RuntimeError('Board file changed during snapshot: ' + item['path'])
                snapshot['backup_verified'].append(item['path'])
        for relative, encoded in snapshot['device_tree'].items():
            target = args.output / 'live_dt' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(encoded))
        if snapshot['boot_fdt']:
            (args.output / 'boot_fdt.dtb').write_bytes(base64.b64decode(snapshot['boot_fdt']))
        (args.output / 'board_snapshot.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
        print(json.dumps({'status': 'READ_ONLY_SNAPSHOT_COMPLETE',
                          'dt_properties': len(snapshot['device_tree']),
                          'recovery_files': len(snapshot['backup_verified']),
                          'output': str(args.output)}))
    finally:
        client.close()


if __name__ == '__main__':
    main()

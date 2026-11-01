"""Back up the installed apps and download sources; never start either runtime."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'eeg_apps_z15'))
from reload_formal_wireless import netsh, wait_board
from run_soak_stage import connect
from run_ssvep_backlog_replay import checked

BRAIN = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
EYE = '/home/xilinx/tobii_z15'


def download_tree(sftp, remote, local, hashes):
    local.mkdir(parents=True, exist_ok=True)
    for item in sftp.listdir_attr(remote):
        source = remote + '/' + item.filename
        target = local / item.filename
        if stat.S_ISDIR(item.st_mode):
            if item.filename != '__pycache__':
                download_tree(sftp, source, target, hashes)
        elif stat.S_ISREG(item.st_mode):
            sftp.get(source, str(target))
            hashes[str(target)] = hashlib.sha256(target.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sources-only', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    client = None
    try:
        netsh('GuardianLoop-Z15')
        wait_board()
        client = connect(host='192.168.50.1')
        client.get_transport().set_keepalive(5)
        report = {'client_date': datetime.now().isoformat(), 'files': {}}
        report['services_before'] = checked(client, 'systemctl show guardianloop-cyton.service guardianloop-web.service -p ActiveState -p MainPID -p NRestarts')
        report['boot_id'] = checked(client, 'cat /proc/sys/kernel/random/boot_id').strip()
        # Snapshot application code/configuration; unchanged media/captures stay
        # in their original directories, outside this transaction's write set.
        archive = '/home/xilinx/brain_eye_backup_' + args.output.name + '.tar.gz'
        paths = ['home/xilinx/tobii_z15', 'home/xilinx/jupyter_notebooks/guardianloop_pynq',
                 'etc/systemd/system/guardianloop-cyton.service',
                 'etc/systemd/system/guardianloop-web.service',
                 'etc/systemd/system/guardianloop-startup.service',
                 'etc/systemd/system/guardianloop-cyton.service.d',
                 'etc/systemd/system/guardianloop-web.service.d',
                 'etc/guardianloop-mi.json', 'boot/boot.py', 'boot/boot.scr']
        excluded = ['*/captures', '*/media', '*/usb_audio_headers', '*/usb_audio_source',
                    '*/__pycache__', '*.jsonl', '*.csv', '*.raw', '*.zip', '*.tar.gz']
        if not args.sources_only:
            checked(client, 'tar ' + ' '.join('--exclude=' + shlex.quote(p) for p in excluded)
                    + ' -czf ' + shlex.quote(archive) + ' -C / ' + ' '.join(map(shlex.quote, paths)), sudo=True)
            report['board_backup'] = archive
            report['board_backup_sha256'] = checked(client, 'sha256sum ' + shlex.quote(archive), sudo=True).split()[0]
            report['backup_excludes'] = excluded
            print('CODE_CONFIG_BOARD_BACKUP_READY ' + archive, flush=True)
        sftp = client.open_sftp()
        brain_local = args.output / 'brain'
        brain_local.mkdir()
        sftp.get(BRAIN + '/release_manifest.json', str(brain_local / 'release_manifest.json'))
        manifest = json.loads((brain_local / 'release_manifest.json').read_text())
        for name, expected in manifest['files'].items():
            target = brain_local / name
            sftp.get(BRAIN + '/' + name, str(target))
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError('Brain file changed: ' + name)
            report['files']['brain/' + name] = actual
        print('BRAIN_SNAPSHOT_VERIFIED ' + str(len(manifest['files'])), flush=True)
        eye_local = args.output / 'eye'
        eye_local.mkdir()
        for folder in ('src', 'tools', 'tests', 'overlay'):
            download_tree(sftp, EYE + '/' + folder, eye_local / folder, report['files'])
            print('EYE_SNAPSHOT_DIRECTORY ' + folder, flush=True)
        for item in sftp.listdir_attr(EYE):
            if stat.S_ISREG(item.st_mode):
                target = eye_local / item.filename
                sftp.get(EYE + '/' + item.filename, str(target))
                report['files']['eye/' + item.filename] = hashlib.sha256(target.read_bytes()).hexdigest()
        sftp.close()
        report['services'] = checked(client, 'systemctl cat guardianloop-cyton.service guardianloop-web.service guardianloop-startup.service')
        report['services_after'] = checked(client, 'systemctl show guardianloop-cyton.service guardianloop-web.service -p ActiveState -p MainPID -p NRestarts')
        report['services_unchanged'] = report['services_before'] == report['services_after']
        report['formal_files_changed'] = False
        report['pl_loaded'] = False
        (args.output / 'snapshot.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'snapshot': str(args.output), 'files': len(report['files']), 'services_unchanged': report['services_unchanged']}), flush=True)
    finally:
        if client is not None:
            client.close()
        netsh('JLU.WIFI')
        for _ in range(20):
            interfaces = subprocess.check_output(['netsh', 'wlan', 'show', 'interfaces']).decode(errors='replace')
            if 'JLU.WIFI' in interfaces:
                break
            time.sleep(.5)
        print('PC_WIFI_RESTORED ' + str('JLU.WIFI' in interfaces), flush=True)


if __name__ == '__main__':
    main()

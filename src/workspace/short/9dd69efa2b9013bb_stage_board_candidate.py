"""Install only a separate, non-autostart candidate and run its read-only gate."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'eeg_apps_z15'))
from reload_formal_wireless import netsh, wait_board
from run_soak_stage import connect
from run_ssvep_backlog_replay import checked

LOCAL = Path(__file__).resolve().parent / 'candidate/eye'
REMOTE = '/home/xilinx/brain_eye_coexist_20261005/eye'
OUTPUT = Path(__file__).resolve().parent / 'output/board_stage_20261005.json'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'


def main():
    client = None
    try:
        netsh('GuardianLoop-Z15'); wait_board()
        client = connect(host='192.168.50.1')
        client.get_transport().set_keepalive(5)
        before = checked(client, 'systemctl show guardianloop-cyton.service guardianloop-web.service -p ActiveState -p MainPID -p NRestarts')
        checked(client, 'test ! -e ' + shlex.quote(REMOTE) + ' && mkdir -p ' + shlex.quote(REMOTE))
        sftp = client.open_sftp()
        hashes = {}
        for folder in ('src', 'tests', 'overlay'):
            sftp.mkdir(REMOTE + '/' + folder)
            for path in sorted((LOCAL / folder).iterdir()):
                if path.is_file() and path.suffix in ('.py', '.h', '.c', '.bit', '.hwh'):
                    relative = folder + '/' + path.name
                    sftp.put(str(path), REMOTE + '/' + relative)
                    hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        for name in ('is4-calibration', 'libtobii_display.so', 'coexist_session.py'):
            sftp.put(str(LOCAL / name), REMOTE + '/' + name)
            hashes[name] = hashlib.sha256((LOCAL / name).read_bytes()).hexdigest()
        sftp.close()
        checked(client, 'mkdir ' + shlex.quote(REMOTE + '/captures')
                + ' && ln -s /home/xilinx/tobii_z15/media ' + shlex.quote(REMOTE + '/media')
                + ' && ln -s /home/xilinx/tobii_z15/bin ' + shlex.quote(REMOTE + '/bin')
                + ' && chmod 755 ' + shlex.quote(REMOTE + '/is4-calibration'))
        # Only the isolated payload is owned by root; no change to original apps.
        checked(client, 'chown -R root:root ' + shlex.quote(REMOTE), sudo=True)
        preflight = checked(client, 'env XILINX_XRT=/usr OPENBLAS_NUM_THREADS=1 '
                            + PYTHON + ' ' + shlex.quote(REMOTE + '/coexist_session.py'), sudo=True)
        tests = checked(client, PYTHON + ' -m unittest discover -s ' + shlex.quote(REMOTE + '/tests')
                        + " -p 'test_*.py'", sudo=True)
        after = checked(client, 'systemctl show guardianloop-cyton.service guardianloop-web.service -p ActiveState -p MainPID -p NRestarts')
        report = {'candidate': REMOTE, 'candidate_files': hashes, 'preflight': preflight,
                  'board_unit_tests': tests, 'services_before': before, 'services_after': after,
                  'services_unchanged': before == after, 'pl_changed': False,
                  'startup_changed': False, 'formal_app_changed': False}
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({key: report[key] for key in ('candidate', 'preflight', 'services_unchanged')}), flush=True)
    finally:
        if client is not None:client.close()
        netsh('JLU.WIFI')
        for _ in range(20):
            state = subprocess.check_output(['netsh', 'wlan', 'show', 'interfaces']).decode(errors='replace')
            if 'JLU.WIFI' in state:break
            time.sleep(.5)
        print('PC_WIFI_RESTORED ' + str('JLU.WIFI' in state), flush=True)


if __name__ == '__main__':main()

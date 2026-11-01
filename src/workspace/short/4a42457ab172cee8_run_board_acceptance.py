"""Dispatch/collect one finite authorized candidate test over board Wi-Fi."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'eeg_apps_z15'))
from reload_formal_wireless import netsh, wait_board
from run_soak_stage import connect
from run_ssvep_backlog_replay import checked

REMOTE = '/home/xilinx/brain_eye_coexist_20261005'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('launch', 'collect', 'software', 'regression'))
    parser.add_argument('--run', required=True)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--locate', action='store_true')
    parser.add_argument('--media', action='store_true')
    parser.add_argument('--shared-pl', action='store_true')
    parser.add_argument('--stop-after', type=int)
    parser.add_argument('--profile-only', action='store_true')
    parser.add_argument('--direct-framebuffer', action='store_true')
    args = parser.parse_args()
    if not args.run.isalnum():raise ValueError('Run identifier must be alphanumeric')
    output = ROOT / 'output' / args.run
    output.mkdir(exist_ok=True)
    client = None
    try:
        netsh('GuardianLoop-Z15');wait_board()
        client = connect(host='192.168.50.1')
        client.get_transport().set_keepalive(5)
        sftp = client.open_sftp()
        if args.action in ('launch', 'regression'):
            active = checked(client, 'systemctl list-units --state=running --no-legend "brain-eye-coexist-*"')
            if active.strip():raise RuntimeError('Wait for the existing finite test to finish before updating the candidate')
            # Only these isolated candidate files are updated, never original apps.
            checked(client, 'mkdir -p ' + REMOTE + '/eye/tools', sudo=True)
            updates = ('src/coexist_guard.py', 'src/hdmi_guide.py', 'tests/test_coexist_guard.py',
                       'src/guide_render.py', 'tests/test_media.py', 'tools/check_local_media_board.py')
            for name in updates:
                temporary = '/home/xilinx/coexist_update_' + Path(name).name
                local = ROOT / 'candidate/eye' / name
                sftp.put(str(local), temporary)
                checked(client, 'install -m 644 ' + shlex.quote(temporary) + ' '
                        + shlex.quote(REMOTE + '/eye/' + name), sudo=True)
                expected = hashlib.sha256(local.read_bytes()).hexdigest()
                actual = checked(client, 'sha256sum ' + shlex.quote(REMOTE + '/eye/' + name)).split()[0]
                if actual != expected:raise RuntimeError('Candidate upload mismatch: ' + name)
            sftp.put(str(ROOT / 'board_acceptance.py'), REMOTE + '/board_acceptance.py')
            preflight = checked(client, 'env XILINX_XRT=/usr OPENBLAS_NUM_THREADS=1 ' + PYTHON
                                + ' ' + REMOTE + '/eye/coexist_session.py', sudo=True)
            tests = checked(client, PYTHON + ' -m unittest discover -s ' + REMOTE
                            + "/eye/tests -p 'test_coexist_guard.py'", sudo=True)
            (output / 'preflight.txt').write_text(preflight + '\n' + tests, encoding='utf-8')
            unit = 'brain-eye-coexist-' + args.run
            command = ('systemd-run --unit=' + unit
                       + ' --property=Type=exec --property=TimeoutStopSec=30'
                       + ' --property=KillMode=control-group --property=SendSIGKILL=no --property=RuntimeMaxSec=' + str(args.seconds + 120)
                       + ' --setenv=XILINX_XRT=/usr --setenv=OPENBLAS_NUM_THREADS=1 '
                       + PYTHON + ' -u ' + REMOTE + '/board_acceptance.py --output ' + REMOTE
                       + '/' + args.run + ' --seconds ' + str(args.seconds))
            if args.locate:command += ' --locate'
            if args.media:command += ' --media'
            if args.shared_pl:command += ' --shared-pl'
            if args.stop_after is not None:command += ' --stop-after ' + str(args.stop_after)
            if args.direct_framebuffer:command += ' --direct-framebuffer'
            if args.action == 'regression':command += ' --software-only'
            print(checked(client, command, sudo=True), flush=True)
        elif args.action == 'software':
            active = checked(client, 'systemctl list-units --state=running --no-legend "brain-eye-coexist-*"')
            if active.strip():raise RuntimeError('Wait for the finite hardware test to finish first')
            local = ROOT / 'candidate/eye/tools/check_renderer_board.py'
            temporary = '/home/xilinx/coexist_update_check_renderer_board.py'
            sftp.put(str(local), temporary)
            checked(client, 'install -m 644 ' + temporary + ' ' + REMOTE + '/eye/tools/check_renderer_board.py', sudo=True)
            before = checked(client, 'systemctl show guardianloop-cyton.service guardianloop-web.service -p MainPID -p NRestarts -p ActiveState')
            tests = 'Not rerun; profile-only' if args.profile_only else checked(client,
                'env OPENBLAS_NUM_THREADS=1 ' + PYTHON + ' -m unittest discover -s '
                + REMOTE + "/eye/tests -p 'test_*.py'", sudo=True)
            profile = checked(client, 'env OPENBLAS_NUM_THREADS=1 ' + PYTHON + ' '
                              + REMOTE + '/eye/tools/check_renderer_board.py --jpeg '
                              + '/home/xilinx/tobii_z15/media_smoke/videos/02/frame_000001.jpg', sudo=True)
            audio = checked(client, 'cat /proc/asound/cards; /home/xilinx/tobii_z15/bin/aplay -l', sudo=True)
            after = checked(client, 'systemctl show guardianloop-cyton.service guardianloop-web.service -p MainPID -p NRestarts -p ActiveState')
            (output / 'software.json').write_text(json.dumps({'tests': tests, 'render_profile': json.loads(profile),
                'audio_devices': audio, 'services_unchanged': before == after}, ensure_ascii=False, indent=2), encoding='utf-8')
            print(tests + '\n' + profile + '\n' + audio, flush=True)
        else:
            status = checked(client, 'systemctl show brain-eye-coexist-' + args.run
                             + '.service -p ActiveState -p SubState -p Result -p ExecMainStatus', sudo=True)
            print(status, flush=True)
            (output / 'unit.txt').write_text(status, encoding='utf-8')
            for name in ('report.json', 'eye.log', 'software_report.json'):
                try:
                    sftp.stat(REMOTE + '/' + args.run + '/' + name)
                    sftp.get(REMOTE + '/' + args.run + '/' + name, str(output / (name + '.download')))
                    (output / (name + '.download')).replace(output / name)
                except FileNotFoundError:print('NOT_READY ' + name, flush=True)
            if 'SubState=running' not in status:
                audit = ('import json, subprocess; from pathlib import Path; from pynq import PL; '
                         's=json.loads(Path("/run/guardianloop/status.json").read_text()); '
                         't=json.loads(Path("/run/guardianloop/telemetry.json").read_text()); '
                         'print(json.dumps({"boot_id":Path("/proc/sys/kernel/random/boot_id").read_text().strip(), '
                         '"current_pl":PL.bitfile_name, "primary":{k:s.get(k) for k in '
                         '("packets_seen","dropped_packets","sequence_gaps","state","valid","filter_backend")}, '
                         '"runtime":t.get("runtime"), "services":subprocess.check_output('
                         '["systemctl","show","guardianloop-cyton.service","guardianloop-web.service",'
                         '"-p","MainPID","-p","NRestarts","-p","ActiveState"],text=True)}))')
                live = checked(client, 'env XILINX_XRT=/usr OPENBLAS_NUM_THREADS=1 ' + PYTHON
                               + ' -c ' + shlex.quote(audit), sudo=True)
                (output / 'live_state.json').write_text(live, encoding='utf-8')
                settled = []
                for _ in range(5):
                    time.sleep(2)
                    with sftp.open('/run/guardianloop/telemetry.json', 'r') as stream:
                        telemetry = json.loads(stream.read())
                    settled.append({key: telemetry.get(key) for key in
                                    ('packets_seen', 'dropped_packets', 'sequence_gaps', 'sample_index', 'runtime')})
                (output / 'settled_state.json').write_text(json.dumps(settled, indent=2), encoding='utf-8')
            if (output / 'report.json').exists() and (output / 'report.json').stat().st_size:
                report = json.loads((output / 'report.json').read_text())
                print(json.dumps({key: report.get(key) for key in ('eye_exit_code', 'error',
                    'pl_restored', 'services_unchanged', 'protected_files_unchanged', 'needs_attention')}), flush=True)
        sftp.close()
    finally:
        if client is not None:client.close()
        netsh('JLU.WIFI')
        for _ in range(20):
            state = subprocess.check_output(['netsh', 'wlan', 'show', 'interfaces']).decode(errors='replace')
            if 'JLU.WIFI' in state:break
            time.sleep(.5)
        print('PC_WIFI_RESTORED ' + str('JLU.WIFI' in state), flush=True)


if __name__ == '__main__':main()

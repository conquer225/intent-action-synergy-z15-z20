"""Stage recorded-only MI virtual control on ARM without changing production or services."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex

from run_soak_stage import connect
from run_ssvep_backlog_replay import checked


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'pynq_guardianloop'
OUT = ROOT / 'eeg_apps_z15/output/mi_virtual_control_20261003'
FILES = ('mi_cued.py', 'mi_cued.html', 'mi_cued_server.py', 'mi_cued_replay.py',
         'mi_cued_acceptance.py', 'mi_virtual_replay.py', 'test_mi_virtual.py', 'test_mi_cued.py')
BOARD_RUNTIME = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
BOARD_PYTHON = '/usr/local/share/pynq-venv/bin/python3'
PROTECTED = (BOARD_RUNTIME, '/etc/default/guardianloop-mi.json',
             '/etc/systemd/system/guardianloop-cyton.service',
             '/etc/systemd/system/guardianloop-web.service')


def protect(client):
    command = 'find ' + ' '.join(shlex.quote(path) for path in PROTECTED)
    command += " -type f ! -path '*/__pycache__/*' -exec sha256sum {} \\;"
    hashes = checked(client, command)
    services = checked(client, 'systemctl is-active guardianloop-cyton.service guardianloop-web.service')
    boot = checked(client, 'cat /proc/sys/kernel/random/boot_id')
    config = checked(client, 'cat /etc/default/guardianloop-mi.json')
    return dict(hashes=hashes, services=services, boot_id=boot, mi_config=config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, help='New absolute child directory under /home/xilinx')
    args = parser.parse_args()
    if not args.stage.startswith('/home/xilinx/mi-virtual-') or any(
            token in args.stage for token in ('..', '\n', '\r', '\\')):
        parser.error('A new /home/xilinx/mi-virtual-* directory is required')
    client = connect()
    try:
        before = protect(client)
        # Do not compete with a human recording in progress.
        recording = json.loads(checked(client, 'cat /run/guardianloop/recording_status.json'))
        if recording.get('active') or recording.get('state') == 'recording':
            raise RuntimeError('Recording is active: isolated ARM acceptance deferred')
        stage = shlex.quote(args.stage)
        checked(client, 'test ! -e ' + stage + ' && mkdir ' + stage)
        manifest = {}
        with client.open_sftp() as sftp:
            for name in FILES:
                source = RUNTIME / name
                sftp.put(str(source), args.stage + '/' + name)
                manifest[name] = hashlib.sha256(source.read_bytes()).hexdigest()
            model = ROOT / 'eeg_apps_z15/output/mi_cued_delivery_20261002_final/experimental_eegnet.npz'
            input_path = ROOT / 'eeg_apps_z15/output/accepted_bench_load_20260927/bench_input.npz'
            for source in (model, input_path):
                sftp.put(str(source), args.stage + '/' + source.name)
                manifest[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
        env = 'env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 '
        env += 'PYTHONPATH=' + shlex.quote(args.stage + ':' + BOARD_RUNTIME) + ' '
        test_output = checked(client, 'cd ' + stage + ' && timeout 45s ' + env + BOARD_PYTHON +
                              ' -m unittest test_mi_cued test_mi_virtual')
        (OUT / 'arm_tests.log').write_text(test_output, encoding='utf-8')
        replay_output = checked(client, 'cd ' + stage + ' && timeout 60s ' + env + BOARD_PYTHON +
            ' mi_virtual_replay.py --model experimental_eegnet.npz --input bench_input.npz --output arm')
        (OUT / 'arm_replay.log').write_text(replay_output, encoding='utf-8')
        (OUT / 'arm').mkdir(exist_ok=False)
        with client.open_sftp() as sftp:
            for child in ('report.json', 'observe/events.jsonl', 'observe/replay.json', 'observe/arrays.npz',
                          'virtual/events.jsonl', 'virtual/replay.json', 'virtual/arrays.npz'):
                local = OUT / 'arm' / child
                local.parent.mkdir(exist_ok=True)
                sftp.get(args.stage + '/arm/' + child, str(local))
        report = json.loads((OUT / 'arm/report.json').read_text(encoding='utf-8'))
        after = protect(client)
        evidence = dict(stage=args.stage, files=manifest, before=before, after=after,
                        production_files_unchanged=before['hashes'] == after['hashes'],
                        services_unchanged=before['services'] == after['services'],
                        boot_unchanged=before['boot_id'] == after['boot_id'],
                        mi_config_unchanged=before['mi_config'] == after['mi_config'],
                        replay_passed=report['passed'], accuracy_scored=False, control_enabled=False)
        evidence['passed'] = all(evidence[key] for key in (
            'production_files_unchanged', 'services_unchanged', 'boot_unchanged',
            'mi_config_unchanged', 'replay_passed'))
        (OUT / 'ARM_PROTECTION.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)
                                               + '\n', encoding='utf-8')
        print(json.dumps({key: value for key, value in evidence.items()
                          if key not in ('before', 'after', 'files')}, ensure_ascii=False))
        if not evidence['passed']:
            raise AssertionError('ARM isolation or replay verification failed')
    finally:
        client.close()


if __name__ == '__main__':
    main()

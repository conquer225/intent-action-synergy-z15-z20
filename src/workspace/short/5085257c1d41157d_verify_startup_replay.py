"""Replay existing Cyton samples through the installed release after its boot check."""

import hashlib
import json
import shlex
import uuid

from deploy_startup import OUT, LEDGER, PROD, SOURCE, PYTHON, connect, sudo, verify, digest
from run_accepted_bench_load import remote


INPUT = SOURCE.parent / 'eeg_apps_z15/output/pl_integrated_candidate_20260929/recorded_input.npz'
REFERENCE = SOURCE.parent / 'eeg_apps_z15/output/ssvep_quality_gate_20260930/post_deploy_1_primary_results.json'


def main():
    ledger = json.loads(LEDGER.read_text(encoding='utf-8'))
    if (OUT / 'replay_audit.json').exists():
        raise RuntimeError('This replay already has an audit; preserve its evidence')
    client = connect()
    stopped = False
    try:
        before = verify(client, ledger, 'before_replay.json')
        if before['boot_id'] == ledger['boot_id_before']:
            raise RuntimeError('Board has not rebooted since startup deployment')
        attempt = uuid.uuid4().hex[:8]
        stage = ledger['stage'] + '/replay-' + attempt
        remote(client, 'mkdir ' + shlex.quote(stage))
        hashes = {'input.npz': hashlib.sha256(INPUT.read_bytes()).hexdigest(),
                  'soak_service_replay.py': hashlib.sha256((SOURCE / 'soak_service_replay.py').read_bytes()).hexdigest(),
                  'replay_stage_trace.py': hashlib.sha256((SOURCE / 'replay_stage_trace.py').read_bytes()).hexdigest()}
        with client.open_sftp() as sftp:
            sftp.put(str(INPUT), stage + '/input.npz')
            sftp.put(str(SOURCE / 'soak_service_replay.py'), stage + '/soak_service_replay.py')
            sftp.put(str(SOURCE / 'replay_stage_trace.py'), stage + '/replay_stage_trace.py')
            for name, expected in hashes.items():
                if digest(sftp, stage + '/' + name) != expected:
                    raise RuntimeError('Replay upload checksum mismatch: ' + name)
        sudo(client, 'systemctl stop guardianloop-cyton.service')
        stopped = True
        invocation = ('cd ' + shlex.quote(stage) + ' && timeout -s TERM -k 5 125 env '
                      'PYTHONPATH=' + shlex.quote(PROD) + ' OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr '
                      + PYTHON + ' soak_service_replay.py --input input.npz --input-kind recorded '
                      '--filter-backend arm --seconds 80 --trace-stages --output result '
                      '--volatile-primary-dir /dev/shm/guardianloop_startup_20261001_' + attempt + '_primary '
                      '--volatile-shadow-dir /dev/shm/guardianloop_startup_20261001_' + attempt + '_shadow')
        print('STARTUP_REPLAY_BEGIN 80 seconds, installed production code, isolated outputs', flush=True)
        try:
            text = remote(client, invocation, timeout=140)
        except RuntimeError as exc:
            (OUT / ('replay_failure_' + attempt + '.txt')).write_text(str(exc), encoding='utf-8')
            raise
        (OUT / 'replay_stdout.txt').write_text(text, encoding='utf-8')
        with client.open_sftp() as sftp:
            for name in ('report.json', 'stages.json', 'primary_results.json', 'monitor.jsonl', 'producer.json'):
                sftp.get(stage + '/result/' + name, str(OUT / ('replay_' + name)))
        report = json.loads((OUT / 'replay_report.json').read_text(encoding='utf-8'))
        results = json.loads((OUT / 'replay_primary_results.json').read_text(encoding='utf-8'))
        audit = {'input_hashes': hashes, 'boot_id': before['boot_id'], 'stage': stage,
                 'packets_consumed': report['packets_consumed'], 'packets_expected': report['packets_expected'],
                 'input_age_p95_ms': report['packet_input_age_p95_ms'],
                 'input_age_max_ms': report['packet_input_age_max_ms'],
                 'total_cpu_s': report['parent_cpu_seconds'] + report['children_cpu_seconds'],
                 'monitor_errors': report['monitor_errors'], 'remaining_children': report['remaining_children'],
                 'error': report['error'], 'filter_backend': report['filter_backend'],
                 'primary_matches_prior_release': results == json.loads(REFERENCE.read_text(encoding='utf-8')),
                 'source': 'offline_replay_not_live', 'live_usb_opened': False}
        audit['passed'] = (audit['packets_consumed'] == audit['packets_expected'] == 20000
                           and audit['input_age_p95_ms'] < 500 and audit['input_age_max_ms'] < 3000
                           and not audit['monitor_errors'] and not audit['remaining_children']
                           and not audit['error'] and audit['filter_backend'] == 'arm'
                           and audit['primary_matches_prior_release'])
        (OUT / 'replay_audit.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
        print('STARTUP_REPLAY_RESULT', json.dumps(audit), flush=True)
        if not audit['passed']:
            raise RuntimeError('Post-boot replay did not pass; inspect its audit')
    finally:
        if stopped:
            sudo(client, 'systemctl start guardianloop-cyton.service')
        client.close()
    client = connect()
    try:
        verify(client, ledger, 'after_replay.json')
    finally:
        client.close()


if __name__ == '__main__':
    main()

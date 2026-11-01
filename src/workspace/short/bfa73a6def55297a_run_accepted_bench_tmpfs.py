"""Repeat accepted bench replay with primary status/telemetry on isolated tmpfs."""
import json
import time

from run_accepted_bench_load import OUT, PROD, PYTHON, SECONDS, connect, remote


def main():
    manifest_path = OUT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (OUT / 'tmpfs-report.json').exists():
        raise RuntimeError('Prior tmpfs report exists; preserve it')
    stage = manifest['stage']
    volatile = '/dev/shm/guardianloop_accepted_bench_' + time.strftime('%Y%m%d_%H%M%S')
    client = connect()
    try:
        manifest['tmpfs_production_before'] = remote(client, 'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        print('TMPFS_BENCH_START', flush=True)
        command = ('cd ' + stage + ' && timeout -s TERM -k 5 205 env '
                   'PYTHONPATH=' + PROD + ' OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr '
                   + PYTHON + ' soak_service_replay.py --input input.npz --input-kind recorded '
                   '--output tmpfs-result --seconds ' + str(SECONDS)
                   + ' --volatile-primary-dir ' + volatile)
        print(remote(client, command), flush=True)
        with client.open_sftp() as sftp:
            for name in ('report.json','producer.json','monitor.jsonl','primary_results.json',
                         'shadow.json','ssvep.json','offline-replay.log'):
                try:
                    sftp.get(stage + '/tmpfs-result/' + name, str(OUT / ('tmpfs-' + name)))
                except FileNotFoundError:
                    pass
        manifest['tmpfs_production_after'] = remote(client, 'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        manifest['tmpfs_path'] = volatile
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        report = json.loads((OUT / 'tmpfs-report.json').read_text(encoding='utf-8'))
        print('TMPFS_REPORT', json.dumps({key: report.get(key) for key in
              ('packets_consumed','packets_expected','packet_input_age_p95_ms',
               'packet_input_age_max_ms','parent_cpu_seconds','children_cpu_seconds',
               'packet_compute_p99_ms','monitor_errors','error')}), flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    main()

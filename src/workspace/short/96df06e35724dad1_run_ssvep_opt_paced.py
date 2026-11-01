"""Paced A/B bench replay of production vs cached SSVEP in isolated Z15 dirs."""
import hashlib
import json
import time
import argparse

from run_accepted_bench_load import PROD, PYTHON, SECONDS, connect, remote
from stage_ssvep_opt_candidate import CANDIDATE, OUT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reverse', action='store_true', help='Second pair in candidate-baseline order')
    args = parser.parse_args()
    label = 'paced2' if args.reverse else 'paced'
    manifest_path = OUT/'candidate_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if not json.loads((OUT/'event_parity.json').read_text())['passed']:
        raise RuntimeError('Event parity must pass first')
    if (OUT/(label+'_baseline_report.json')).exists() or (OUT/(label+'_candidate_report.json')).exists():
        raise RuntimeError('Paced evidence already exists; preserve it')
    manifest[label+'_acceptance'] = {
        'all_packets': SECONDS*250,
        'event_parity_exact_except_scores_atol_1e-9': True,
        'primary_results_exact': True,
        'no_errors_or_remaining_children': True,
        'candidate_input_age_p95_ms_lt': 500,
        'candidate_input_age_max_ms_lt': 3000,
        'candidate_total_cpu_reduction_at_least': 0.10,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    stage, candidate = manifest['stage'], manifest['candidate']
    client = connect()
    try:
        client.get_transport().set_keepalive(15)
        manifest[label+'_production_before'] = remote(client, 'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        cases = (('candidate', candidate+':'+PROD), ('baseline', PROD)) if args.reverse else (('baseline', PROD), ('candidate', candidate+':'+PROD))
        for name, module_path in cases:
            print('PACED_START', name, flush=True)
            output = stage+'/'+label+'-opt-'+name
            volatile = '/dev/shm/ssvep_opt_'+name+'_'+time.strftime('%Y%m%d_%H%M%S')
            command = ('cd '+stage+' && timeout -s TERM -k 5 205 env '
                'PYTHONPATH='+module_path+' OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr '
                +PYTHON+' soak_service_replay.py --input input.npz --input-kind recorded '
                '--output '+output+' --seconds '+str(SECONDS)
                +' --volatile-primary-dir '+volatile)
            print(remote(client, command, timeout=225)[-1500:], flush=True)
            with client.open_sftp() as sftp:
                for filename in ('report.json','producer.json','monitor.jsonl','primary_results.json',
                                 'shadow.json','ssvep.json','offline-replay.log'):
                    try:
                        sftp.get(output+'/'+filename, str(OUT/(label+'_'+name+'_'+filename)))
                    except FileNotFoundError:
                        pass
            report = json.loads((OUT/(label+'_'+name+'_report.json')).read_text())
            print('PACED_DONE', name, json.dumps({k:report[k] for k in
                ('packets_consumed','packet_input_age_p95_ms','packet_input_age_max_ms',
                 'parent_cpu_seconds','children_cpu_seconds','packet_compute_p99_ms')}), flush=True)
        manifest[label+'_production_after'] = remote(client, 'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        with client.open_sftp() as sftp:
            manifest['production_hashes_after'] = {name: hashlib.sha256(sftp.open(PROD+'/'+name).read()).hexdigest()
                for name in CANDIDATE}
        manifest_path.write_text(json.dumps(manifest, indent=2))
    finally:
        client.close()


if __name__ == '__main__':
    main()

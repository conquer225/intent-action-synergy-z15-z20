"""Isolated SSVEP candidate replay with shadow endpoints on tmpfs."""
import hashlib
import json
import time

from run_accepted_bench_load import PROD, PYTHON, SECONDS, ROOT, connect, remote
from stage_ssvep_opt_candidate import CANDIDATE, OUT


def main():
    manifest_path = OUT/'candidate_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if (OUT/'volatile_shadow_report.json').exists():
        raise RuntimeError('Volatile shadow run already exists; preserve it')
    stage, candidate = manifest['stage'], manifest['candidate']
    tag = time.strftime('%Y%m%d_%H%M%S')
    primary = '/dev/shm/ssvep_opt_primary_'+tag
    shadow = '/dev/shm/ssvep_opt_shadow_'+tag
    client = connect()
    try:
        with client.open_sftp() as sftp:
            sftp.put(str(ROOT/'pynq_guardianloop/soak_service_replay.py'),
                     stage+'/soak_service_replay.py')
        manifest['volatile_shadow_harness_sha256'] = hashlib.sha256((ROOT/'pynq_guardianloop/soak_service_replay.py').read_bytes()).hexdigest()
        manifest['volatile_shadow_production_before'] = remote(client, 'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        command = ('cd '+stage+' && timeout -s TERM -k 5 205 env '
            'PYTHONPATH='+candidate+':'+PROD+' OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr '
            +PYTHON+' soak_service_replay.py --input input.npz --input-kind recorded '
            '--output '+stage+'/volatile-shadow-result --seconds '+str(SECONDS)
            +' --volatile-primary-dir '+primary+' --volatile-shadow-dir '+shadow)
        print('VOLATILE_SHADOW_START', flush=True)
        print(remote(client, command, timeout=225)[-1200:], flush=True)
        with client.open_sftp() as sftp:
            for filename in ('report.json','producer.json','monitor.jsonl','primary_results.json',
                             'offline-replay.log'):
                sftp.get(stage+'/volatile-shadow-result/'+filename,
                         str(OUT/('volatile_shadow_'+filename)))
            for name in ('ssvep.json','shadow.json'):
                sftp.get(shadow+'/'+name, str(OUT/('volatile_shadow_'+name)))
        manifest['volatile_shadow_production_after'] = remote(client, 'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        with client.open_sftp() as sftp:
            manifest['volatile_shadow_production_hashes_after'] = {
                name:hashlib.sha256(sftp.open(PROD+'/'+name).read()).hexdigest() for name in CANDIDATE}
        manifest_path.write_text(json.dumps(manifest, indent=2))
        result = json.loads((OUT/'volatile_shadow_report.json').read_text())
        print('VOLATILE_SHADOW_REPORT', json.dumps({key:result.get(key) for key in
              ('packets_consumed','packet_input_age_p95_ms','packet_input_age_max_ms',
               'parent_cpu_seconds','children_cpu_seconds','packet_compute_p99_ms','error')}),flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    main()

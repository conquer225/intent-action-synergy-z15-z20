"""Replay the same bench trace through immutable production and staged SSVEP candidate."""
import json

from run_accepted_bench_load import OUT as PREVIOUS, PROD, ROOT, PYTHON, connect, remote
from stage_ssvep_opt_candidate import OUT


def main():
    manifest = json.loads((OUT/'candidate_manifest.json').read_text())
    stage, candidate = manifest['stage'], manifest['candidate']
    client = connect()
    try:
        with client.open_sftp() as sftp:
            sftp.put(str(ROOT/'eeg_apps_z15/replay_ssvep_bench_events.py'),
                     stage+'/replay_ssvep_bench_events.py')
        for name, path in (('baseline', PROD), ('candidate', candidate+':'+PROD)):
            local = OUT/('bridge_'+name+'_events.json')
            if local.exists():
                raise RuntimeError('Bridge evidence already exists: '+str(local))
            output = stage+'/bridge-'+name+'-events'
            print('BRIDGE_START', name, flush=True)
            command = ('cd '+stage+' && timeout -s TERM -k 5 105 env PYTHONPATH='
                       +path+' OPENBLAS_NUM_THREADS=1 '+PYTHON
                       +' replay_ssvep_bench_events.py --input input.npz --output '+output)
            print(remote(client, command, timeout=115), flush=True)
            with client.open_sftp() as sftp:
                sftp.get(output+'/events.json', str(local))
        manifest['bridge_production_after'] = remote(client, 'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        (OUT/'candidate_manifest.json').write_text(json.dumps(manifest, indent=2))
    finally:
        client.close()


if __name__ == '__main__':
    main()

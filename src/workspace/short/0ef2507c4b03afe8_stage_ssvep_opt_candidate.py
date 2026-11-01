"""Stage existing cached CCA/SQI candidate separately from the Z15 live service."""
import hashlib
import json

from run_accepted_bench_load import OUT as PREVIOUS, PROD, ROOT, PYTHON, connect, remote


OUT = ROOT/'eeg_apps_z15/output/ssvep_detail_opt_20260927'
CANDIDATE = {
    'ssvep_shadow.py': ROOT/'pynq_guardianloop/ssvep_shadow.py',
    'ssvep_stream.py': ROOT/'eeg_apps_z15/ssvep_stream.py',
    'ssvep_core.py': ROOT/'eeg_apps_z15/ssvep_core.py',
    'cyton_sqi.py': ROOT/'pynq_guardianloop/cyton_sqi.py',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest_path = OUT/'candidate_manifest.json'
    if manifest_path.exists():
        raise RuntimeError('Candidate already staged; preserve it')
    stage = json.loads((PREVIOUS/'manifest.json').read_text())['stage']
    candidate = stage+'/candidate_opt'
    client = connect()
    try:
        before = remote(client, 'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        with client.open_sftp() as sftp:
            sftp.mkdir(candidate)
            original = OUT/'production_snapshot'
            original.mkdir(exist_ok=False)
            for name, source in CANDIDATE.items():
                sftp.get(PROD+'/'+name, str(original/name))
                sftp.put(str(source), candidate+'/'+name)
            for name, source in {
                'input.npz': PREVIOUS/'bench_input.npz',
                'profile_ssvep_detail.py': ROOT/'eeg_apps_z15/profile_ssvep_detail.py',
                'ssvep_causal_protocol.json': ROOT/'eeg_apps_z15/ssvep_causal_protocol.json',
                'ssvep_candidate_sos.npy': ROOT/'eeg_apps_z15/output/ssvep_causal_20260926/candidate_sos.npy',
                'test_ssvep_cache.py': ROOT/'eeg_apps_z15/test_ssvep_cache.py',
                'test_ssvep_stream.py': ROOT/'eeg_apps_z15/test_ssvep_stream.py',
                'test_ssvep_shadow.py': ROOT/'pynq_guardianloop/test_ssvep_shadow.py',
            }.items():
                sftp.put(str(source), candidate+'/'+name)
        manifest = {'stage': stage, 'candidate': candidate,
                    'production_before': before,
                    'production_sha256': {name: sha(OUT/'production_snapshot'/name) for name in CANDIDATE},
                    'candidate_sha256': {name: sha(source) for name, source in CANDIDATE.items()},
                    'bench_input_sha256': sha(PREVIOUS/'bench_input.npz'),
                    'scope': 'Isolated candidate only; no service/PL modification'}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        tests = remote(client, 'cd '+candidate+' && timeout -s TERM -k 5 90 env '
            'PYTHONPATH='+candidate+':'+PROD+' OPENBLAS_NUM_THREADS=1 '+PYTHON
            +' -m unittest test_ssvep_cache test_ssvep_stream test_ssvep_shadow -v 2>&1', timeout=100)
        (OUT/'candidate_tests.txt').write_text(tests, encoding='utf-8')
        print(tests[-4000:], flush=True)
        print('CANDIDATE_MICRO_START', flush=True)
        detail = remote(client, 'cd '+candidate+' && timeout -s TERM -k 5 100 env '
            'PYTHONPATH='+candidate+':'+PROD+' OPENBLAS_NUM_THREADS=1 '+PYTHON
            +' profile_ssvep_detail.py', timeout=110)
        print(detail[-2000:], flush=True)
        with client.open_sftp() as sftp:
            sftp.get(candidate+'/detail_report.json', str(OUT/'candidate_detail.json'))
        manifest['production_after'] = remote(client, 'systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState')
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    finally:
        client.close()


if __name__ == '__main__':
    main()

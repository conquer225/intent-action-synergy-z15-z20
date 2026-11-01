"""Stage and run read-only SSVEP substep timing on Z15."""
import json

from run_accepted_bench_load import OUT as PREVIOUS, PROD, ROOT, PYTHON, connect, remote


def main():
    folder = ROOT/'eeg_apps_z15/output/ssvep_detail_opt_20260927'
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder/'baseline_detail.json'
    if destination.exists():
        raise RuntimeError('Baseline detail exists; preserve it')
    stage = json.loads((PREVIOUS/'manifest.json').read_text())['stage']
    client = connect()
    try:
        with client.open_sftp() as sftp:
            sftp.put(str(ROOT/'eeg_apps_z15/profile_ssvep_detail.py'), stage+'/profile_ssvep_detail.py')
        print(remote(client, 'cd '+stage+' && timeout -s TERM -k 5 105 env PYTHONPATH='
                     +PROD+' OPENBLAS_NUM_THREADS=1 '+PYTHON+' profile_ssvep_detail.py', timeout=115), flush=True)
        with client.open_sftp() as sftp:
            sftp.get(stage+'/detail_report.json', str(destination))
    finally:
        client.close()


if __name__ == '__main__':
    main()

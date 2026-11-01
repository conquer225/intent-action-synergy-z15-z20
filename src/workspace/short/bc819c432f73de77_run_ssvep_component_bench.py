"""Run isolated board-side SSVEP component timing on the staged bench trace."""
import json

from run_accepted_bench_load import OUT, PROD, ROOT, PYTHON, connect, remote


def main():
    manifest_path = OUT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (OUT / 'micro_ssvep_report.json').exists():
        raise RuntimeError('Prior component benchmark exists; preserve it')
    stage = manifest['stage']
    client = connect()
    try:
        with client.open_sftp() as sftp:
            sftp.put(str(ROOT / 'eeg_apps_z15/benchmark_ssvep_components.py'), stage + '/benchmark_ssvep_components.py')
        command = ('cd ' + stage + ' && timeout -s TERM -k 5 105 env '
                   'PYTHONPATH=' + PROD + ' OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr '
                   + PYTHON + ' benchmark_ssvep_components.py')
        print(remote(client, command, timeout=115), flush=True)
        with client.open_sftp() as sftp:
            sftp.get(stage + '/micro_ssvep_report.json', str(OUT / 'micro_ssvep_report.json'))
    finally:
        client.close()


if __name__ == '__main__':
    main()

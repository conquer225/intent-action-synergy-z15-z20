"""Execute a read-only ARM kernel benchmark without stopping production."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from run_accepted_bench_load import connect, remote, PROD, PYTHON


def main():
    destination = HERE.parent/'output/pl_primary_filter_q31_20260927/arm_micro.json'
    if destination.exists():
        raise FileExistsError(destination)
    previous = json.loads((HERE.parent/'output/accepted_bench_load_20260927/manifest.json').read_text())
    client = connect()
    try:
        result = {'before':remote(client,'systemctl show guardianloop-cyton guardianloop-web -p ActiveState -p MainPID -p NRestarts')}
        with client.open_sftp() as sftp:
            result['production_sqi_sha256'] = hashlib.sha256(sftp.open(PROD+'/cyton_sqi.py').read()).hexdigest()
        stdin, stdout, stderr = client.exec_command('env OPENBLAS_NUM_THREADS=1 '+PYTHON+
            ' - --production '+PROD+' --input '+previous['stage']+'/input.npz',timeout=120)
        stdin.write((HERE/'benchmark_arm_filter.py').read_text())
        stdin.channel.shutdown_write()
        output = stdout.read().decode()
        error = stderr.read().decode()
        if stdout.channel.recv_exit_status():
            raise RuntimeError(error)
        result['microbenchmark'] = json.loads(output)
        result['after'] = remote(client,'systemctl show guardianloop-cyton guardianloop-web -p ActiveState -p MainPID -p NRestarts')
        destination.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result['microbenchmark'],indent=2))
    finally:
        client.close()


if __name__ == '__main__':
    main()

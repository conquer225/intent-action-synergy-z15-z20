"""Dispatch a private, finite same-release recorded workload; production remains live."""
import argparse
import json
from pathlib import Path
import shlex
import re

import stage_server as upload
from stage_media import STATE,PYTHON


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--performance',action='store_true')
    parser.add_argument('--label');args=parser.parse_args()
    label='eeg-video-load' if args.performance else 'eeg-smoke-current' if args.smoke else 'eeg-load-current'
    if args.label:
        if not re.fullmatch('eeg-[a-z0-9-]{1,40}',args.label):raise ValueError('Invalid workload label')
        label=args.label
    state=json.loads(STATE.read_text());remote=state['remote'];runtime=state['replay_runtime']
    c=upload.trial.connect('192.168.2.99')
    try:
        if upload.trial.execute(c,'test -e '+shlex.quote(remote+'/'+label)+' && echo EXISTS || true').strip():
            raise ValueError('Existing workload output is preserved; use a new label')
        manifest=json.loads(upload.trial.execute(c,'cat /home/xilinx/jupyter_notebooks/guardianloop_pynq/release_manifest.json'))
        names=list(manifest['files'])
        if any(Path(name).name!=name for name in names):raise ValueError('Unsafe release artifact')
        hashes=upload.trial.execute(c,'sha256sum '+' '.join(shlex.quote(runtime+'/'+name) for name in names),root=True)
        actual={line.split()[1].rsplit('/',1)[-1]:line.split()[0] for line in hashes.splitlines()}
        if actual!=manifest['files']:raise ValueError('Private workload no longer matches production release')
        command=['systemd-run','--unit='+state['prefix']+'-'+label,'--uid=xilinx',
            '--property=RuntimeMaxSec=400s','--property=MemoryMax=512M','--property=LimitCORE=0',
            'env','XILINX_XRT=/usr','OPENBLAS_NUM_THREADS=1',PYTHON,runtime+'/mi_multitask_replay.py',
            '--input',runtime+'/bench_input.npz','--output',remote+'/'+label,'--seconds','20' if args.smoke else '220',
            '--filter-backend','arm','--mi-experimental-model',runtime+'/experimental_rms_eegnet.npz',
            '--allow-experimental-mi','--mi-web-port','0',
            '--volatile-primary-dir','/dev/shm/'+state['prefix']+'-'+label+'-primary',
            '--volatile-shadow-dir','/dev/shm/'+state['prefix']+'-'+label+'-shadow']
        command+=['--performance-only'] if args.performance else ['--trace-stages']
        print(upload.trial.execute(c,shlex.join(command),root=True))
        print('PRIVATE_RECORDED_LOAD_STARTED; production files and USB not touched',flush=True)
    finally:c.close()


if __name__=='__main__':main()

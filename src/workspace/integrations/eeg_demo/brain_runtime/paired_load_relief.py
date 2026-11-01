"""Finite ARM-only comparison; production acquisition is restored by systemd."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import threading


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case-timeout',type=int,default=230)
    parser.add_argument('--scheduled-only',action='store_true')
    args=parser.parse_args()
    if not 200 <= args.case_timeout <= 260:
        raise ValueError('Replay deadline must be finite and include model startup')
    runtime=args.runtime.resolve();output=args.output.resolve()
    if runtime.parent!=Path(__file__).resolve().parent or output.parent!=runtime.parent:
        raise ValueError('Replay paths must belong to this private stage')
    output.mkdir(exist_ok=False)
    inactive=subprocess.run(['systemctl','is-active','guardianloop-cyton'],text=True,
                            capture_output=True,check=False).stdout.strip()
    if inactive!='inactive':
        raise ValueError('Production acquisition must be stopped before replay')
    results=[]
    try:
        cases=(
            ('original',['--audit-seed-candidate']),
            ('array_async',['--array-covariance','--array-covariance-source',str(runtime/'covariance_array_source.py'),
                            '--async-seed-candidate','--audit-seed-candidate']),
        )
        page=output/'page.json'
        if args.scheduled_only:
            cases=(('array_scheduled',['--array-covariance','--array-covariance-source',str(runtime/'covariance_array_source.py'),
                '--async-seed-candidate','--audit-seed-candidate','--page-policy-file',str(page)]),)
        for name,options in cases:
            lease_stop=threading.Event();lease_thread=None
            def refresh_lease():
                while not lease_stop.is_set():
                    temporary=page.with_suffix('.part')
                    temporary.write_text(json.dumps(dict(page='video',mode='scripted_hdmi_replay',
                        physical_output_enabled=False,updated_monotonic=time.monotonic())))
                    temporary.replace(page)
                    lease_stop.wait(.5)
            if args.scheduled_only:
                lease_thread=threading.Thread(target=refresh_lease,daemon=True);lease_thread.start()
            command=[sys.executable,str(runtime/'mi_multitask_replay.py'),'--performance-only',
                '--input',str(runtime/'bench_input.npz'),'--output',str(output/name),'--seconds','156',
                '--filter-backend','arm','--mi-experimental-model',str(runtime/'experimental_rms_eegnet.npz'),
                '--allow-experimental-mi','--mi-web-port','0',
                '--volatile-primary-dir','/dev/shm/'+runtime.parent.name+'-'+output.name+'-'+name+'-primary',
                '--volatile-shadow-dir','/dev/shm/'+runtime.parent.name+'-'+output.name+'-'+name+'-shadow',*options]
            print('BEGIN '+name,flush=True)
            started=time.monotonic();timed_out=False
            with (output/(name+'.log')).open('w') as log:
                run=subprocess.Popen(command,cwd=runtime,stdout=log,stderr=subprocess.STDOUT,
                                     start_new_session=True,env=os.environ.copy())
                try:
                    run.wait(timeout=args.case_timeout)
                except subprocess.TimeoutExpired:
                    timed_out=True
                finally:
                    # This group contains only our /dev/null replay and its children.
                    try:os.killpg(run.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:run.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(run.pid,signal.SIGKILL);run.wait(timeout=3)
                    lease_stop.set()
                    if lease_thread:lease_thread.join(timeout=2)
            report_path=output/name/'report.json'
            report=json.loads(report_path.read_text()) if report_path.exists() else {}
            results.append(dict(case=name,exit_code=run.returncode,timed_out=timed_out,
                                wall_seconds=time.monotonic()-started,report=report))
            (output/'paired-report.json').write_text(json.dumps(results,indent=2))
            print(json.dumps(dict(case=name,exit_code=run.returncode,
                packets=report.get('packets_consumed'),error=report.get('error'))),flush=True)
            if run.returncode:
                raise RuntimeError('Replay failed; retain evidence and stop comparison')
    finally:
        subprocess.run(['systemctl','start','guardianloop-cyton'],check=True,timeout=25)


if __name__=='__main__':main()

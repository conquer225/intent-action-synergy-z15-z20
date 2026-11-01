"""Two paced recorded-only ARM loads; no USB, MMIO, PL loads or motor commands."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',type=Path,required=True)
    parser.add_argument('--scheduled',action='store_true')
    parser.add_argument('--attempt',type=int,default=1,choices=range(1,24))
    parser.add_argument('--only',choices=('reference','hardened'))
    parser.add_argument('--idle-mi',action='store_true',help='Match video-page use with no automatic MI cue requests')
    tracing=parser.add_mutually_exclusive_group()
    tracing.add_argument('--trace-stages',action='store_true',help='Isolated per-stage wall and CPU timings')
    tracing.add_argument('--trace-primary-stalls',action='store_true')
    parser.add_argument('--without-telemetry',action='store_true',help='Diagnostic only: omit display waveforms in the private replay')
    parser.add_argument('--without-mi',action='store_true',help='Diagnostic only: do not launch the private idle MI lane')
    placement=parser.add_mutually_exclusive_group()
    placement.add_argument('--split-worker-cpus',action='store_true')
    placement.add_argument('--eeg-cpu0',action='store_true',help='Private CPU division comparison only')
    parser.add_argument('--background-nice',type=int,choices=(0,10),default=0)
    parser.add_argument('--async-primary-candidate',action='store_true')
    parser.add_argument('--reader-batch-candidate',action='store_true')
    parser.add_argument('--mi-tap-batch-candidate',action='store_true')
    parser.add_argument('--trace-fast-path-stalls',action='store_true')
    parser.add_argument('--trace-primary-submit',action='store_true')
    args=parser.parse_args();stage=args.stage.resolve()
    if args.eeg_cpu0 and (not args.idle_mi or not args.async_primary_candidate
            or args.attempt != 23 or args.background_nice):
        raise ValueError('Single-core EEG belongs to the uninstrumented private attempt 23')
    if args.reader_batch_candidate and (args.attempt not in (19,20,21,22,23) or not args.async_primary_candidate):
        raise ValueError('Reader batch is restricted to private attempts 19..23')
    if args.mi_tap_batch_candidate and (args.attempt not in (20,21,22,23) or not args.reader_batch_candidate
                                      or args.without_mi):
        raise ValueError('MI tap batching requires private attempts 20..23 with MI')
    if args.trace_fast_path_stalls and (args.attempt not in (21,22) or not args.mi_tap_batch_candidate
                                      or args.trace_stages or args.trace_primary_stalls):
        raise ValueError('Fast-path diagnostic is restricted to private attempts 21/22')
    if args.trace_primary_submit and (args.attempt != 22 or not args.trace_fast_path_stalls):
        raise ValueError('Submission diagnosis is restricted to private attempt 22')
    if args.async_primary_candidate and (not args.idle_mi or args.trace_stages
            or args.trace_primary_stalls or args.only != 'hardened'):
        raise ValueError('Primary worker requires the uninstrumented hardened idle replay')
    if args.without_mi and not args.idle_mi:
        raise ValueError('MI ablation requires the idle recorded-only harness')
    if args.trace_primary_stalls and not args.idle_mi:
        raise ValueError('Primary stall tracing requires the idle recorded-only harness')
    if args.background_nice and not (args.idle_mi and args.split_worker_cpus):
        raise ValueError('Background priority requires the idle role-split replay')
    if stage!=Path(__file__).resolve().parent or stage.parent!=Path('/home/xilinx') or not stage.name.startswith('gl-prewear-'):
        raise ValueError('Replay must stay in its pinned private stage')
    result=[]
    suffix=('-scheduled'+str(args.attempt)) if args.scheduled else ''
    prefix=('scheduled'+str(args.attempt)+'-') if args.scheduled else ''
    cases=[(name,folder) for name,folder in (('reference','original_runtime'),('hardened','runtime'))
           if args.only is None or args.only==name]
    for name,folder in cases:
        name+=suffix
        runtime=stage/folder;output=stage/('load-'+name)
        if output.exists():raise ValueError('Do not overwrite retained replay results')
        command=[sys.executable,str(runtime/'mi_multitask_replay.py'),'--performance-only',
            '--input',str(runtime/'bench_input.npz'),'--output',str(output),'--seconds','156',
            '--filter-backend','arm','--array-covariance','--async-seed-candidate','--audit-seed-candidate',
            '--mi-web-port','0','--volatile-primary-dir','/dev/shm/'+stage.name+'-'+name+'-primary',
            '--volatile-shadow-dir','/dev/shm/'+stage.name+'-'+name+'-shadow']
        if not args.without_mi:
            command.extend(['--allow-experimental-mi','--mi-experimental-model',
                            str(runtime/'experimental_rms_eegnet.npz')])
        if args.idle_mi:
            command[1]=str(runtime/'soak_service_replay.py');command.remove('--performance-only')
        if args.async_primary_candidate:
            command.append('--async-primary-candidate')
        if args.reader_batch_candidate:
            command.append('--reader-batch-candidate')
        if args.mi_tap_batch_candidate:
            command.append('--mi-tap-batch-candidate')
        if args.trace_fast_path_stalls:
            command.append('--trace-fast-path-stalls')
        if args.trace_primary_submit:
            command.append('--trace-primary-submit')
        if args.trace_stages:
            command.append('--trace-stages')
        if args.trace_primary_stalls:
            command.append('--trace-primary-stalls')
        if args.without_telemetry:
            command.append('--without-telemetry')
        if args.split_worker_cpus:
            command.append('--split-worker-cpus')
        if args.eeg_cpu0:
            command.append('--eeg-cpu0')
        if args.background_nice:
            command.extend(['--background-nice',str(args.background_nice)])
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',GL_SEED_EXECUTION='sync',
                 GL_COVARIANCE_STORAGE='array',PYTHONPATH=str(runtime))
        env.pop('GL_PAGE_POLICY_PATH',None);env.pop('GL_HDMI_LIVE_STATE',None)
        policy_stop=threading.Event();policy_thread=None
        if args.scheduled:
            policy=stage/('page-'+name+'.json')
            command.extend(['--page-policy-file',str(policy)])
            def refresh_policy():
                while not policy_stop.is_set():
                    temporary=policy.with_suffix('.new')
                    temporary.write_text(json.dumps(dict(page='video',updated_monotonic=time.monotonic(),
                        mode='scripted_hdmi_replay',physical_output_enabled=False)))
                    temporary.replace(policy)
                    policy_stop.wait(.5)
            policy_thread=threading.Thread(target=refresh_policy,daemon=True);policy_thread.start()
        started=time.monotonic()
        with (stage/('load-'+name+'.log')).open('w') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,cwd=runtime,start_new_session=True)
            try:process.wait(timeout=225)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
                raise RuntimeError('Recorded replay exceeded its finite deadline')
            finally:
                # Only this /dev/null replay's process group; not production.
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                policy_stop.set()
                if policy_thread:policy_thread.join(timeout=2)
        report_path=output/'report.json'
        report=json.loads(report_path.read_text()) if report_path.exists() else {}
        log=(output/'offline-replay.log').read_text() if (output/'offline-replay.log').exists() else ''
        covariance_loaded='COVARIANCE_MODEL_READY:' in log and 'COVARIANCE_MODEL_DISABLED:' not in log
        result.append(dict(case=name,exit_code=process.returncode,covariance_loaded=covariance_loaded,
                           mi_disabled_diagnostic=args.without_mi,
                           wall_seconds=time.monotonic()-started,report=report))
        (stage/(prefix+'load-summary.json')).write_text(json.dumps(result,indent=2))
        print(json.dumps(dict(case=name,exit_code=process.returncode,packets=report.get('packets_consumed'),error=report.get('error'))),flush=True)
        if process.returncode:raise RuntimeError('Private recorded replay failed; production untouched')
        if not covariance_loaded:raise RuntimeError('Emotion model was not loaded; reject this performance evidence')
    if args.only:
        print('SINGLE_RECORDED_LOAD_COMPLETE_NOT_ACCURACY_TEST',flush=True)
        return
    reference=json.loads((stage/('load-reference'+suffix)/'primary_results.json').read_text())
    candidate=json.loads((stage/('load-hardened'+suffix)/'primary_results.json').read_text())
    comparison=dict(reference_windows=len(reference),hardened_windows=len(candidate),matched=[],differences=[],
                    source='recorded_bench_not_accuracy',raw_usb_opened=False,pl_loaded=False)
    # Compare numerical/model fields, not wall clocks or wearing metadata.
    for i,(a,b) in enumerate(zip(reference,candidate)):
        a,b=a['result'],b['result']
        fields=('state','valid','calibration_current','level','score','emotion')
        diffs=[k for k in fields if a.get(k)!=b.get(k)]
        (comparison['differences'] if diffs else comparison['matched']).append(dict(window=i+1,fields=diffs))
    comparison['same_window_count']=len(reference)==len(candidate)
    (stage/(prefix+'load-comparison.json')).write_text(json.dumps(comparison,indent=2))
    print('RECORDED_LOAD_COMPLETE_NOT_ACCURACY_TEST',flush=True)


if __name__=='__main__':main()

"""Private recorded-load diagnostics. Never writes release files or opens USB/PL."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shlex
import time

import run_hdmi_live as live


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'phone_video_upload/output/compute_relief_20261009'
STAGE = '/home/xilinx/gl-prewear-20261008-kA18D9'


def collect(client, attempt):
    state = live.board.execute(client, shlex.join(['systemctl', 'show',
        'gl-prewear-profile%d-20261009.service' % attempt, '-p', 'ActiveState', '--value']), root=True).strip()
    if state not in ('inactive', 'failed'):
        raise ValueError('Replay is still running; no complete report is available')
    stage = STAGE if attempt == 4 else json.loads((OUT / 'stage.json').read_text())['remote']
    source = stage + '/load-hardened-scheduled' + str(attempt)
    target = OUT / ('profile' + str(attempt))
    target.mkdir(parents=True, exist_ok=True)
    with client.open_sftp() as ftp:
        ftp.get(source + '/report.json', str(target / 'report.json'))
        report = json.loads((target / 'report.json').read_text())
        names = ['primary_results.json', 'producer.json', 'offline-replay.log', 'monitor.jsonl']
        if report['stage_instrumentation']:
            names.extend(('stages.json', 'slow_packets.json', 'telemetry_stages.json'))
        elif report.get('primary_stall_instrumentation') or report.get('fast_path_stall_instrumentation'):
            names.extend(('primary_stalls.json','slow_packets.json'))
        missing = []
        for name in names:
            if report.get('error'):
                try:
                    ftp.stat(source + '/' + name)
                except FileNotFoundError:
                    missing.append(name)
                    continue
            ftp.get(source + '/' + name, str(target / name))
        if missing:
            (target / 'missing-failed-run-artifacts.json').write_text(json.dumps(missing))
        ftp.get(stage + '/load-hardened-scheduled%d.log' % attempt, str(target / 'driver.log'))
    ranked = []
    if report['stage_instrumentation']:
        trace = json.loads((target / 'stages.json').read_text())
        ranked = sorted(trace['stages'].items(), key=lambda item: item[1]['max_wall_s'], reverse=True)
    print(json.dumps(dict(report=report, stages=ranked[:12]), indent=2))


def stage(client):
    OUT.mkdir(parents=True, exist_ok=True)
    state = OUT / 'stage.json'
    if state.exists():
        raise ValueError('Inspect the retained stage; do not overwrite it')
    remote = live.board.execute(client, 'mktemp -d /home/xilinx/gl-prewear-compute-20261009-XXXXXX').strip()
    code = ('import shutil,sys; from pathlib import Path; s=Path(sys.argv[1]); t=Path(sys.argv[2]); '
        "shutil.copytree(s/'runtime',t/'runtime',ignore=shutil.ignore_patterns('__pycache__')); "
        "shutil.copytree(s/'runtime',t/'original_runtime',ignore=shutil.ignore_patterns('__pycache__'))")
    live.board.execute(client, shlex.join([live.board.PYTHON, '-c', code, STAGE, remote]))
    files = [('pynq_guardianloop/' + name, 'runtime/' + name) for name in
        ('cyton_guardianloop.py', 'cyton_sqi.py', 'replay_stage_trace.py', 'test_primary_windows.py',
         'test_cyton_sqi.py', 'benchmark_primary_windows.py', 'test_replay_stage_trace.py')]
    files.append(('phone_video_upload/prewear_load.py', 'prewear_load.py'))
    with client.open_sftp() as ftp:
        for source, destination in files:
            ftp.put(str(ROOT / source), remote + '/' + destination)
    state.write_text(json.dumps(dict(remote=remote, production_changed=False), indent=2))
    command = ['env', 'XILINX_XRT=/usr', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
        'PYTHONPATH=' + remote + '/runtime', live.board.PYTHON]
    output = live.board.execute(client, shlex.join(command + ['-m', 'unittest',
        'test_primary_windows', 'test_cyton_sqi', 'test_replay_stage_trace']) + ' 2>&1', root=True)
    (OUT / 'array-tests.txt').write_text(output)
    print(output)
    if 'OK' not in output:
        raise RuntimeError('Private array tests failed')
    output = live.board.execute(client, shlex.join(command + [remote + '/runtime/benchmark_primary_windows.py']), root=True)
    (OUT / 'window-benchmark.json').write_text(output)
    print(output)


def start(client, attempt, trace, without_telemetry=False, without_mi=False, replay_cpu=None,
          split_worker_cpus=False, background_nice=0, trace_primary_stalls=False,
          async_primary_candidate=False, reader_batch_candidate=False,
          mi_tap_batch_candidate=False, trace_fast_path_stalls=False, trace_primary_submit=False):
    if attempt == 4:
        raise ValueError('The retained baseline profile was already run')
    if split_worker_cpus and (replay_cpu is not None or trace):
        raise ValueError('Role split must start with both CPUs and without timing probes')
    if background_nice not in (0,10) or (background_nice and not split_worker_cpus):
        raise ValueError('Background priority requires the isolated role-split replay')
    if trace and trace_primary_stalls:
        raise ValueError('Choose only one tracing mode')
    if reader_batch_candidate and (attempt not in (19,20,21,22,23) or not async_primary_candidate):
        raise ValueError('Reader batching requires the primary worker in private attempts 19..23')
    if mi_tap_batch_candidate and (attempt not in (20,21,22,23) or not reader_batch_candidate or without_mi):
        raise ValueError('MI batching belongs to private attempts 20..23 with MI')
    if trace_fast_path_stalls and (attempt not in (21,22) or not mi_tap_batch_candidate or trace or trace_primary_stalls):
        raise ValueError('Fast-path diagnosis belongs to private attempts 21/22')
    if trace_primary_submit and (attempt != 22 or not trace_fast_path_stalls):
        raise ValueError('Submission diagnosis belongs to private attempt 22')
    if async_primary_candidate and (attempt not in (17,18,19,20,21,22,23) or trace or trace_primary_stalls):
        raise ValueError('Primary worker is restricted to private attempts 17..23')
    remote = json.loads((OUT / 'stage.json').read_text())['remote']
    tests_state = live.board.execute(client, shlex.join(['systemctl', 'show',
        'gl-compute-tests-20261009.service', 'gl-compute-recovery-tests-20261009.service',
        'gl-primary-final-tests17-20261009.service', 'gl-primary-final-tests18-20261009.service',
        'gl-reader-tests19-20261009.service', 'gl-reader-final-tests19-20261009.service',
        'gl-reader-benchmark19-20261009.service',
        'gl-reader-final-benchmark19-20261009.service',
        'gl-mi-tap-tests20-20261009.service',
        'gl-submit-tests22-20261010.service', 'gl-handoff-tests23-20261010.service',
        'gl-handoff-final-tests23-20261010.service',
        'gl-handoff-verified-tests23-20261010.service',
        *('gl-compute-recovery-tests%d-20261009.service' % i for i in range(7,24)),
        '-p', 'ActiveState', '--value']), root=True).splitlines()
    if any(state in ('active','activating','deactivating') for state in tests_state):
        raise ValueError('Do not contaminate performance timing with concurrent tests')
    profiles = live.board.execute(client, shlex.join(['systemctl', 'show',
        *('gl-prewear-profile%d-20261009.service' % i for i in range(4,24)),
        '-p', 'ActiveState', '--value']), root=True).splitlines()
    if any(state in ('active','activating','deactivating') for state in profiles):
        raise ValueError('Only one isolated performance replay may run at a time')
    with client.open_sftp() as ftp:
        ftp.put(str(ROOT / 'phone_video_upload/prewear_load.py'), remote + '/prewear_load.py')
        ftp.put(str(ROOT / 'pynq_guardianloop/soak_service_replay.py'), remote + '/runtime/soak_service_replay.py')
        if trace_primary_stalls or trace_fast_path_stalls:
            ftp.put(str(ROOT / 'pynq_guardianloop/replay_stage_trace.py'), remote + '/runtime/replay_stage_trace.py')
    command = ['systemd-run',
        '--unit=gl-prewear-profile%d-20261009' % attempt, '--property=RuntimeMaxSec=250',
        '--property=TimeoutStopSec=10', '--property=Nice=0', 'env', 'XILINX_XRT=/usr',
        'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1', live.board.PYTHON, remote + '/prewear_load.py',
        '--stage', remote, '--scheduled', '--attempt', str(attempt), '--only', 'hardened',
        '--idle-mi']
    if replay_cpu is not None:
        command.insert(5, '--property=CPUAffinity='+str(replay_cpu))
    if trace:
        command.append('--trace-stages')
    if trace_primary_stalls:
        command.append('--trace-primary-stalls')
    if async_primary_candidate:
        command.append('--async-primary-candidate')
    if reader_batch_candidate:
        command.append('--reader-batch-candidate')
    if mi_tap_batch_candidate:
        command.append('--mi-tap-batch-candidate')
    if trace_fast_path_stalls:
        command.append('--trace-fast-path-stalls')
    if trace_primary_submit:
        command.append('--trace-primary-submit')
    if without_telemetry:
        command.append('--without-telemetry')
    if without_mi:
        command.append('--without-mi')
    if split_worker_cpus:
        command.append('--split-worker-cpus')
    if background_nice:
        command.extend(['--background-nice',str(background_nice)])
    print(live.board.execute(client, shlex.join(command), root=True))


def refresh(client, attempt):
    remote = json.loads((OUT / 'stage.json').read_text())['remote']
    active = live.board.execute(client, shlex.join(['systemctl', 'show',
        *('gl-prewear-profile%d-20261009.service' % i for i in range(4,24)),
        '-p', 'ActiveState', '--value']), root=True).splitlines()
    if any(state in ('active','activating','deactivating') for state in active):
        raise ValueError('Never change a running replay runtime')
    names = ('cyton_guardianloop.py', 'cyton_sqi.py', 'replay_stage_trace.py',
        'test_primary_windows.py', 'benchmark_primary_windows.py', 'test_calibration_main.py',
        'test_primary_window_main.py', 'telemetry_json.py', 'test_telemetry_json.py',
        'test_telemetry_publish.py', 'test_small_batch.py', 'benchmark_telemetry_json.py')
    if attempt >= 10:
        names += ('mi_cued.py', 'mi_acquisition.py', 'mi_rms_live_virtual.py',
                  'test_mi_snapshot_cost.py', 'benchmark_mi_idle.py', 'test_mi_cued.py',
                  'test_mi_acquisition.py', 'test_mi_reader_tap.py',
                  'test_mi_rms_live_virtual.py', 'test_mi_virtual.py')
    hashes = {}
    with client.open_sftp() as ftp:
        for name in names:
            source = ROOT / 'pynq_guardianloop' / name
            ftp.put(str(source), remote + '/runtime/' + name)
            hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    code = ('import sys,json,hashlib; from pathlib import Path; p=Path(sys.argv[1]); '
        'h=json.loads(sys.argv[2]); assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==v '
        'for n,v in h.items()); print("PRIVATE_SOURCES_VERIFIED")')
    print(live.board.execute(client, shlex.join([live.board.PYTHON, '-c', code,
        remote + '/runtime', json.dumps(hashes)])))
    label = 'mi-snapshot-candidate' if attempt >= 10 else 'telemetry-candidate'
    (OUT / (label+'-hashes.json')).write_text(json.dumps(hashes, indent=2))
    command = ['env', 'XILINX_XRT=/usr', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
        'PYTHONPATH=' + remote + '/runtime', live.board.PYTHON]
    output = live.board.execute(client, shlex.join(command + [remote + '/runtime/benchmark_primary_windows.py']), root=True)
    (OUT / ('resource-window-benchmark'+(str(attempt) if attempt >= 10 else '')+'.json')).write_text(output)
    print(output)


def prepare_primary(client):
    remote = json.loads((OUT / 'stage.json').read_text())['remote']
    if remote != '/home/xilinx/gl-prewear-compute-20261009-LcGhCQ':
        raise ValueError('Primary candidate must use the retained private replay stage')
    states = live.board.execute(client, shlex.join(['systemctl', 'show',
        'gl-primary-final-tests17-20261009.service', 'gl-primary-final-tests18-20261009.service',
        *('gl-prewear-profile%d-20261009.service' % i for i in range(4,24)),
        *('gl-compute-recovery-tests%d-20261009.service' % i for i in range(7,24)),
        '-p', 'ActiveState', '--value']), root=True).splitlines()
    if any(state in ('active', 'activating', 'deactivating') for state in states):
        raise ValueError('Private runtime cannot be changed during a test')
    code = ('import sys,shutil,json,hashlib; from pathlib import Path; p=Path(sys.argv[1]); '
        "b=p/'before-primary17'; b.mkdir(); "
        "names=('cyton_guardianloop.py','soak_service_replay.py'); "
        "[shutil.copy2(p/'runtime'/n,b/n) for n in names]; "
        "print(json.dumps({n:hashlib.sha256((b/n).read_bytes()).hexdigest() for n in names}))")
    backup = live.board.execute(client, shlex.join([live.board.PYTHON, '-c', code, remote]))
    hashes = {}
    with client.open_sftp() as ftp:
        for name in ('cyton_guardianloop.py','primary_window.py','async_primary.py',
                     'test_async_primary.py','soak_service_replay.py'):
            source = ROOT / 'pynq_guardianloop' / name
            ftp.put(str(source), remote+'/runtime/'+name)
            hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    verify = ('import sys,json,hashlib; from pathlib import Path; p=Path(sys.argv[1]); '
        'h=json.loads(sys.argv[2]); assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==v '
        'for n,v in h.items()); print("PRIMARY_PRIVATE_SOURCES_VERIFIED")')
    print(live.board.execute(client, shlex.join([live.board.PYTHON,'-c',verify,
        remote+'/runtime',json.dumps(hashes)])))
    (OUT/'primary-candidate-hashes17.json').write_text(json.dumps(dict(
        candidate=hashes, before=json.loads(backup), production_changed=False), indent=2))


def tests(client, recovery_only, attempt):
    remote = json.loads((OUT / 'stage.json').read_text())['remote']
    label = ('recovery-tests' if recovery_only else 'tests')+('' if attempt<=6 else str(attempt))
    names = ['test_calibration_main', 'test_primary_windows', 'test_cyton_sqi',
        'test_replay_stage_trace', 'test_primary_stream_recovery', 'test_calibration_session']
    if not recovery_only:
        names.insert(0, 'test_primary_window_main')
    if attempt>=8:
        names.extend(('test_telemetry_json','test_telemetry_publish','test_small_batch'))
    if attempt>=10:
        names.extend(('test_mi_snapshot_cost','test_mi_cued','test_mi_acquisition',
                      'test_mi_reader_tap','test_mi_rms_live_virtual','test_mi_virtual'))
    if attempt in (17,18,19):
        names = ['test_async_primary', 'test_calibration_main', 'test_primary_window_main',
                 'test_primary_stream_recovery', 'test_calibration_session',
                 'test_primary_windows', 'test_replay_cpu_policy']
    command = ['systemd-run', '--unit=gl-compute-' + label + '-20261009',
        '--property=RuntimeMaxSec='+('480' if attempt>=17 else '240'),
        '--property=TimeoutStopSec=10', '--property=Nice=0',
        '--property=StandardOutput=file:' + remote + '/linux-compute-' + label + '.log',
        '--property=StandardError=inherit', 'env', 'XILINX_XRT=/usr', 'OPENBLAS_NUM_THREADS=1',
        'OMP_NUM_THREADS=1', 'GL_TEST_FATIGUE_MODEL=' + remote + '/runtime/cyton_fatigue_overlap4.json',
        'PYTHONPATH=' + remote + '/runtime', live.board.PYTHON, '-m', 'unittest', '-v', *names]
    if attempt in (17,18,19):
        command.insert(command.index('env')+1,
            'GL_TEST_PRIMARY_REFERENCE='+remote+'/before-primary17/cyton_guardianloop.py')
    print(live.board.execute(client, shlex.join(command), root=True))


def observe(client, attempt):
    if attempt<6:
        raise ValueError('Display observation is supported for attempts 6 through 23')
    remote = json.loads((OUT / 'stage.json').read_text())['remote']
    with client.open_sftp() as ftp:
        ftp.put(str(ROOT / 'phone_video_upload/prewear_observe.py'), remote + '/prewear_observe.py')
    print(live.board.execute(client, shlex.join(['systemd-run', '--unit=gl-compute-observe%d-20261009' % attempt,
        '--property=RuntimeMaxSec=240', '--property=TimeoutStopSec=10', live.board.PYTHON,
        remote + '/prewear_observe.py', '--base', '/home/xilinx/gl-hdmi-live-20261008-ea117349',
        '--stage', remote, '--seconds', '220', '--label', 'actual' if attempt==6 else 'actual'+str(attempt)]), root=True))


def test_result(client, recovery_only, attempt):
    remote = json.loads((OUT / 'stage.json').read_text())['remote']
    label = ('recovery-tests' if recovery_only else 'tests')+('' if attempt<=6 else str(attempt))
    path = remote + '/linux-compute-' + label + '.log'
    state = live.board.execute(client, shlex.join(['systemctl', 'show', 'gl-compute-' + label + '-20261009.service',
        '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus']), root=True)
    print(state)
    if 'ActiveState=active' in state:
        print(live.board.execute(client, shlex.join(['tail', '-n', '3', path]), root=True))
        return
    with client.open_sftp() as ftp:
        ftp.get(path, str(OUT / ('linux-compute-' + label + '.log')))
    output = (OUT / ('linux-compute-' + label + '.log')).read_text()
    print(output)
    if 'Result=success' not in state or 'ExecMainStatus=0' not in state or '\nOK\n' not in output:
        raise RuntimeError('Linux regressions did not pass')


def health(client):
    snapshot = live.request(client)
    player = snapshot.get('player') or {}
    system = player.get('system') or {}
    ident=player.get('session_id','')
    names=['guardianloop-cyton.service','guardianloop-web.service']
    if re.fullmatch('play-[a-f0-9]{8}',ident):names.append(ident+'.service')
    print(live.board.execute(client,shlex.join(['systemctl','show',*names,
        '-p','Id','-p','ActiveState','-p','MainPID','-p','NRestarts']),root=True))
    print(live.board.execute(client,'ip -br addr',root=True))
    print(json.dumps(dict(state=player.get('state'), frame=player.get('frame'),
        page=system.get('page'), stimulus=system.get('stimulus_enabled'),
        physical=system.get('physical_output_enabled')), indent=2))


def video(client, attempt):
    snapshot = live.request(client)
    player = snapshot.get('player') or {}
    if player.get('state') not in ('playing','menu','buffering','paused'):
        raise ValueError('Use only the existing player; never launch or load PL')
    identifier = 'afbb05f8cef54ef9a7ddadbf2613b0e6'
    if not any(v['id'] == identifier and v['prepared'] for v in snapshot['videos']):
        raise ValueError('The pinned 20 fps comparison video is unavailable')
    command = live.request(client, dict(action='video', id=identifier))
    for _ in range(20):
        player = live.request(client).get('player') or {}
        receipt = player.get('command_receipt') or {}
        if receipt.get('id') == command['command_id']:
            system = player.get('system') or {}
            result = dict(receipt=receipt, page=system.get('page'),state=player.get('state'),
                          stimulus=system.get('stimulus_enabled'),
                          physical=system.get('physical_output_enabled'))
            (OUT / ('video-state%d.json' % attempt)).write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
            if (receipt.get('state') != 'applied' or result['page'] != 'video'
                    or result['stimulus'] is not False or result['physical'] is not False):
                raise RuntimeError('Silent video comparison page was not safely applied')
            return
        time.sleep(.2)
    raise RuntimeError('Video page not yet acknowledged; do not start comparison')


def benchmark_telemetry(client):
    remote = json.loads((OUT / 'stage.json').read_text())['remote']
    command = ['env', 'XILINX_XRT=/usr', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
               'PYTHONPATH='+remote+'/runtime', live.board.PYTHON,
               remote+'/runtime/benchmark_telemetry_json.py']
    output = live.board.execute(client, shlex.join(command), root=True)
    (OUT / 'telemetry-benchmark.json').write_text(output)
    print(output)


def benchmark_mi(client):
    remote = json.loads((OUT / 'stage.json').read_text())['remote']
    script = remote+'/runtime/benchmark_mi_idle.py'
    # -c keeps the reference PYTHONPATH first, not the candidate script directory.
    runner = 'import runpy,sys; p=sys.argv.pop(1); runpy.run_path(p,run_name="__main__")'
    rows = []
    for folder, deferred in (('original_runtime', False), ('runtime', True)):
        command = ['env', 'XILINX_XRT=/usr', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
                   'PYTHONPATH='+remote+'/'+folder, live.board.PYTHON, '-c', runner, script]
        if deferred:
            command.append('--defer-snapshot')
        rows.append(json.loads(live.board.execute(client, shlex.join(command), root=True)))
    keys = ('snapshot_sha256','raw_sha256','filtered_sha256','observations')
    equal = all(rows[0][k] == rows[1][k] for k in keys)
    result = dict(reference=rows[0], candidate=rows[1], observations_and_filters_equal=equal)
    (OUT / 'mi-idle-benchmark.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if not equal:
        raise RuntimeError('Deferred MI observations changed the numerical output')


def audit(client):
    state = json.loads((ROOT / 'phone_video_upload/output/hdmi_live_user_controlled_20261008/state.json').read_text())
    code = ('import hashlib,json,sys; from pathlib import Path; p=Path(sys.argv[1]); '
        'h=json.loads(sys.argv[2]); changed=[n for n,v in h.items() '
        'if hashlib.sha256((p/n).read_bytes()).hexdigest()!=v]; '
        'print(json.dumps(dict(checked=len(h),changed=changed, '
        'boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip())))')
    output = live.board.execute(client, shlex.join([live.board.PYTHON, '-c', code,
        str(Path(state['formal_entry']).parent).replace('\\', '/'), json.dumps(state['formal_hashes'])]))
    result = json.loads(output)
    result['same_boot'] = result['boot_id'] == state['boot']
    (OUT / 'formal-audit.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if result['changed'] or not result['same_boot']:
        raise RuntimeError('Formal software or board boot changed during isolated work')


def summarize(attempt):
    """Keep failed timing evidence separate from calculation and safety checks."""
    from prewear_observe import frame_progress
    folder=OUT/('profile'+str(attempt))
    report=json.loads((folder/'report.json').read_text())
    rows=json.loads((folder/'primary_results.json').read_text())
    results=[row['result'] for row in rows]
    monitor=[json.loads(line) for line in (folder/'monitor.jsonl').read_text().splitlines()]
    display_rows=json.loads((OUT/('display-observations-actual'+str(attempt)+'.json')).read_text())
    progress=frame_progress(display_rows)
    (OUT/('display-frame-progress'+str(attempt)+'.json')).write_text(json.dumps(progress,indent=2))
    completed=next((i for i,row in enumerate(results) if row.get('calibration_current')==15
                    and row.get('calibration_retained') is True),None)
    retained=completed is not None and all(row.get('calibration_current')==15
        and row.get('calibration_retained') is True for row in results[completed:])
    final=results[-1]
    withdrew=(final.get('valid') is False and final.get('reason')=='SERVICE_STOPPED_OR_STREAM_TIMEOUT'
              and (final.get('emotion') or {}).get('valid') is False)
    reference=json.loads((OUT/'profile13/primary_results.json').read_text())
    def indexed(source):
        first={}
        for row in source:
            value=row['result']
            if 'window' in value:
                # A later backlog withdrawal must not overwrite the computed result.
                first.setdefault((value['window'],value.get('packets_seen')),value)
        return first
    before,after=indexed(reference),indexed(rows)
    common=sorted(set(before)&set(after))
    fields=('state','valid','calibration_current','calibration_retained','level','score',
            'perclos','smoothed_perclos','last_inference_window','emotion')
    differences=[dict(window=k[0],packets_seen=k[1],fields=[n for n in fields
                  if before[k].get(n)!=after[k].get(n)]) for k in common
                 if any(before[k].get(n)!=after[k].get(n) for n in fields)]
    reasons=dict(Counter(row.get('reason') for row in results if not row.get('valid')))
    safe_display=(bool(display_rows) and not any('error' in row or row.get('physical') is not False
                    or row.get('stimulus') is not False for row in display_rows)
                  and len({row.get('session') for row in display_rows})==1
                  and all(row.get('state') in ('playing','buffering') and row.get('page')=='video' for row in display_rows))
    buffering=sum(row.get('state')=='buffering' for row in display_rows)
    including_buffering=frame_progress([dict(row,state='playing') if row.get('state')=='buffering'
        and row.get('page')=='video' else row for row in display_rows])
    result=dict(attempt=attempt,scope='156s recorded video-page load, not accuracy or optical measurement',
        requested_seconds=report['requested_seconds'],packets=report['packets_consumed'],
        complete=report['packets_consumed']==report['packets_expected'],
        errors=report['monitor_errors'],error=report['error'],remaining_children=report['remaining_children'],
        calibration_retained_after_completion=retained,results_withdrawn_at_end=withdrew,
        states=dict(Counter(row.get('state') for row in results)),reasons=reasons,
        emotion_predictions=sum((row.get('emotion') or {}).get('state')=='prediction' for row in results),
        backlog_invalidations=sum(reasons.get(name,0) for name in
            ('PROCESSING_BACKLOG','PRIMARY_WORKER_BACKLOG','PRIMARY_WORKER_QUEUE_FULL',
             'PRIMARY_WORKER_RESULT_STALE')),
        input_age_p95_ms=report['packet_input_age_p95_ms'],input_age_max_ms=report['packet_input_age_max_ms'],
        input_age_limit_500ms_met=report['packet_input_age_max_ms']<=500,
        stream_resets=max((row.get('runtime') or {}).get('primary_stream_resets',0) for row in monitor),
        model_reference=dict(common_windows=len(common),reference_windows=len(before),candidate_windows=len(after),
            differences=differences,reference_only=sorted(set(before)-set(after)),candidate_only=sorted(set(after)-set(before)),
            note='First output at aligned window and packet count; later withdrawals counted separately; missing windows explicit'),
        display=progress,display_including_buffering=including_buffering,
        buffering_observations=buffering,display_session_scope_unchanged=safe_display,
        published_intervals_16fps_met=(safe_display and not buffering and bool(progress['intervals'])
                                       and progress['intervals_below16']==0),
        physical_control_tested=False,optical_measurement=False)
    (folder/'verification-summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


def finish(client, attempt):
    remote = json.loads((OUT / 'stage.json').read_text())['remote']
    state = live.board.execute(client, shlex.join(['systemctl', 'show',
        'gl-compute-observe%d-20261009.service' % attempt, '-p', 'ActiveState', '--value']), root=True).strip()
    if state != 'inactive':
        raise ValueError('Wait for the finite display observation before changing pages')
    with client.open_sftp() as ftp:
        name='display-observations-actual'+('' if attempt==6 else str(attempt))+'.json'
        ftp.get(remote + '/' + name, str(OUT / name))
    from prewear_observe import frame_progress
    progress = frame_progress(json.loads((OUT / name).read_text()))
    (OUT / ('display-frame-progress%d.json' % attempt)).write_text(json.dumps(progress, indent=2))
    command = live.request(client, {'action': 'force_stop'})
    for _ in range(15):
        snapshot = live.request(client)
        player = snapshot.get('player') or {}
        receipt = player.get('command_receipt') or {}
        if receipt.get('id') == command['command_id']:
            system = player.get('system') or {}
            result = dict(receipt=receipt, page=system.get('page'),
                stimulus=system.get('stimulus_enabled'), physical=system.get('physical_output_enabled'),
                user_controlled=snapshot.get('user_controlled'), player_state=player.get('state'))
            (OUT / ('finished-state'+('' if attempt==6 else str(attempt))+'.json')).write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
            if receipt.get('state') != 'applied' or result['page'] != 'home':
                raise RuntimeError('Diagnostic return to home was not applied')
            return
        time.sleep(.2)
    raise RuntimeError('Return to home has not yet acknowledged; player was not closed')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('collect', 'health', 'audit', 'finish', 'unit', 'stage', 'start', 'refresh', 'tests', 'test-result', 'observe','benchmark-telemetry','benchmark-mi','video','summarize','prepare-primary'))
    parser.add_argument('--attempt', type=int, choices=range(4, 24), default=4)
    tracing=parser.add_mutually_exclusive_group()
    tracing.add_argument('--trace-stages', action='store_true')
    tracing.add_argument('--trace-primary-stalls', action='store_true')
    parser.add_argument('--without-telemetry', action='store_true')
    parser.add_argument('--without-mi', action='store_true')
    parser.add_argument('--replay-cpu', type=int, choices=(0,1),
                        help='Diagnostic affinity for the private replay and its children only')
    parser.add_argument('--split-worker-cpus', action='store_true')
    parser.add_argument('--background-nice', type=int, choices=(0,10), default=0)
    parser.add_argument('--async-primary-candidate', action='store_true')
    parser.add_argument('--reader-batch-candidate', action='store_true')
    parser.add_argument('--mi-tap-batch-candidate', action='store_true')
    parser.add_argument('--trace-fast-path-stalls', action='store_true')
    parser.add_argument('--trace-primary-submit', action='store_true')
    parser.add_argument('--recovery-only', action='store_true')
    args = parser.parse_args()
    if args.action=='summarize':
        summarize(args.attempt)
        return
    client = live.board.upload.trial.connect('192.168.2.99')
    try:
        if args.action == 'collect':
            collect(client, args.attempt)
        elif args.action == 'health':
            health(client)
        elif args.action == 'video':
            video(client,args.attempt)
        elif args.action == 'audit':
            audit(client)
        elif args.action == 'benchmark-telemetry':
            benchmark_telemetry(client)
        elif args.action == 'benchmark-mi':
            benchmark_mi(client)
        elif args.action == 'finish':
            finish(client,args.attempt)
        elif args.action == 'stage':
            stage(client)
        elif args.action == 'start':
            start(client, args.attempt, args.trace_stages,args.without_telemetry,args.without_mi,
                  args.replay_cpu,args.split_worker_cpus,args.background_nice,args.trace_primary_stalls,
                  args.async_primary_candidate,args.reader_batch_candidate,
                  args.mi_tap_batch_candidate,args.trace_fast_path_stalls,args.trace_primary_submit)
        elif args.action == 'prepare-primary':
            prepare_primary(client)
        elif args.action == 'refresh':
            refresh(client,args.attempt)
        elif args.action == 'tests':
            tests(client, args.recovery_only,args.attempt)
        elif args.action == 'test-result':
            test_result(client, args.recovery_only,args.attempt)
        elif args.action == 'observe':
            observe(client,args.attempt)
        else:
            print(live.board.execute(client, shlex.join(['systemctl', 'show',
                'gl-prewear-profile%d-20261009.service' % args.attempt,
                '-p', 'ActiveState', '-p', 'SubState', '-p', 'Result', '-p', 'ExecMainStatus',
                '-p', 'ExecMainStartTimestamp']), root=True))
            remote = STAGE if args.attempt == 4 else json.loads((OUT / 'stage.json').read_text())['remote']
            print(live.board.execute(client, shlex.join(['tail', '-n', '1',
                remote + '/load-hardened-scheduled%d/monitor.jsonl' % args.attempt]), root=True))
    finally:
        client.close()


if __name__ == '__main__':
    main()

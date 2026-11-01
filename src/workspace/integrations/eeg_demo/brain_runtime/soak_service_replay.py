"""Paced replay through the real main loop; PL is opt-in and USB is never opened."""
import argparse
import importlib.util
import inspect
import contextlib
import functools
import json
import multiprocessing
import os
from pathlib import Path
import resource
import subprocess
import sys
import threading
import time

import numpy as np
import cyton_guardianloop as live
from cyton_trial_recorder import TrialRecorder, atomic_json
from guardianloop_web import TelemetryResponseCache
from seed_shadow import SeedShadow

_BASE_TELEMETRY_WORKER = live._telemetry_worker


def configure_replay_worker(cpu, nice=0):
    if nice not in (0, 10):
        raise ValueError('Private background priority must be 0 or 10')
    if cpu is not None:
        os.sched_setaffinity(0, {cpu})
    if nice:
        os.setpriority(os.PRIO_PROCESS, 0, nice)


def replay_cpu_roles(split, eeg_cpu0):
    if split and eeg_cpu0:
        raise ValueError('Choose one private CPU profile')
    return dict(parent=0 if split or eeg_cpu0 else None,
                background=0 if eeg_cpu0 else 1 if split else None,
                primary='inherit' if eeg_cpu0 else '0,1')


def replay_ssvep_worker(*args, page_policy_file=None, cpu=None, nice=0):
    configure_replay_worker(cpu, nice)
    # Spawned workers must receive the replay source marker in their own process.
    import ssvep_acquisition
    from ssvep_shadow import SSVEPShadow
    if page_policy_file:
        from page_scheduled_replay import ssvep_factory
        ssvep_acquisition.SSVEPShadow = functools.partial(ssvep_factory, page_policy_file, source='replay')
    else:
        ssvep_acquisition.SSVEPShadow = functools.partial(SSVEPShadow, source='replay')
    return ssvep_acquisition._worker(*args)


def replay_telemetry_worker(pending, cpu, nice=0):
    configure_replay_worker(cpu, nice)
    # The telemetry writer uses fork: dispatch through the saved, unwrapped target.
    return _BASE_TELEMETRY_WORKER(pending)


def replay_mi_worker(*args, cpu, nice=0):
    configure_replay_worker(cpu, nice)
    import mi_acquisition
    return mi_acquisition._mi_worker(*args)


def array_covariance_factory(stream_class):
    def create(channel_map, storage=None):
        return stream_class(channel_map, storage='array')
    return create


def process_stats(pid):
    try:
        fields = Path('/proc/%d/stat' % pid).read_text().split()
        return {'pid':pid, 'cpu_ticks':int(fields[13])+int(fields[14]),
                'nice':int(fields[18]),
                'rss_kib':int(fields[23])*os.sysconf('SC_PAGE_SIZE')//1024,
                'cpu_affinity':sorted(os.sched_getaffinity(pid))}
    except (FileNotFoundError, ProcessLookupError):
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--page-policy-file',type=Path,
                   help='Private scripted HDMI lease; optional lanes reset on page changes')
    p.add_argument('--output', required=True)
    p.add_argument('--seconds', type=int, default=1800)
    tracing = p.add_mutually_exclusive_group()
    tracing.add_argument('--trace-stages', action='store_true')
    tracing.add_argument('--trace-primary-stalls', action='store_true',
                         help='Isolated ARM diagnostic: primary wall/thread CPU/switch counters only')
    p.add_argument('--array-covariance', action='store_true',
                   help='Private array-buffer candidate; model/filter arithmetic unchanged')
    p.add_argument('--array-covariance-source',type=Path,
                   help='Explicit private source beside this harness; never replace production files')
    p.add_argument('--record-raw', action='store_true',
                   help='Record replay packets only in the private output directory')
    p.add_argument('--async-seed-candidate', action='store_true',
                   help='Replay-only bounded worker for the SEED shadow; never live')
    p.add_argument('--async-primary-candidate', action='store_true')
    p.add_argument('--reader-batch-candidate', action='store_true')
    p.add_argument('--mi-tap-batch-candidate', action='store_true')
    p.add_argument('--trace-fast-path-stalls', action='store_true')
    p.add_argument('--audit-seed-candidate', action='store_true',
                   help='Audit isolated SEED state transitions and input age')
    p.add_argument('--without-telemetry', action='store_true',
                   help='Isolated diagnostic ablation; not a deployment mode')
    placement = p.add_mutually_exclusive_group()
    placement.add_argument('--split-worker-cpus', action='store_true',
                   help='Private replay only: reader CPU 0, MI/telemetry/SSVEP CPU 1; async primary both')
    placement.add_argument('--eeg-cpu0', action='store_true',
                   help='Private ARM replay only: all EEG workers CPU 0, leaving CPU 1 for display')
    p.add_argument('--background-nice', type=int, choices=(0,10), default=0,
                   help='Private replay only: lower MI/telemetry/SSVEP ordinary priority; parent unchanged')
    p.add_argument('--volatile-primary-dir',
                   help='Fresh isolated tmpfs directory for telemetry/status, matching live /run storage')
    p.add_argument('--volatile-shadow-dir',
                   help='Fresh isolated tmpfs directory for SSVEP/SEED shadow status; replay diagnostic only')
    p.add_argument('--reader-fault-after', type=int,
                   help='Inject a terminal reader report after N packets; isolated replay only')
    p.add_argument('--reader-fault-kind', choices=('serial_io_error','queue_full','serial_eof'),
                   default='serial_io_error')
    p.add_argument('--force-rail', action='store_true',
                   help='Isolated synthetic O1/O2 ADC saturation; never deploy as live behavior')
    p.add_argument('--input-kind', choices=('recorded', 'synthetic'), default='recorded')
    p.add_argument('--mi-experimental-model', type=Path)
    p.add_argument('--allow-experimental-mi', action='store_true')
    p.add_argument('--mi-web-port', type=int, default=0,
                   help='Private MI replay server; 0 selects an ephemeral loopback port')
    p.add_argument('--filter-backend', choices=('arm', 'pl'), default='arm',
                   help='PL requires an isolated boot, stopped live service, and a fresh DMA owner')
    p.add_argument('--pause-at', type=int, help='Pause producer after this many input samples')
    p.add_argument('--pause-seconds', type=float, default=0.)
    p.add_argument('--rail-from', type=int, help='Start O1/O2 rail injection at this input sample')
    p.add_argument('--rail-to', type=int, help='Stop O1/O2 rail injection at this input sample')
    p.add_argument('--trace-primary-submit', action='store_true')
    args = p.parse_args()
    if args.trace_primary_submit and not args.trace_fast_path_stalls:
        raise ValueError('Detailed submission tracing requires the private fast-path trace')
    if args.mi_tap_batch_candidate and (not args.reader_batch_candidate
            or not args.async_primary_candidate or not args.allow_experimental_mi):
        raise ValueError('MI tap batching requires the recorded reader/primary candidate and MI')
    if args.trace_fast_path_stalls and (not args.async_primary_candidate
            or args.trace_stages or args.trace_primary_stalls):
        raise ValueError('Fast-path tracing requires the isolated asynchronous candidate alone')
    if args.reader_batch_candidate and not args.async_primary_candidate:
        raise ValueError('Reader batching requires the isolated primary worker')
    if args.async_primary_candidate and (args.filter_backend != 'arm'
            or args.trace_stages or args.trace_primary_stalls):
        raise ValueError('Primary candidate requires uninstrumented isolated ARM replay')
    if args.trace_primary_stalls and args.filter_backend != 'arm':
        raise ValueError('Primary stall tracing is ARM replay only')
    if args.background_nice and not args.split_worker_cpus:
        raise ValueError('Background priority requires the isolated role-split replay')
    if args.eeg_cpu0 and (not args.async_primary_candidate or args.background_nice
            or args.trace_stages or args.trace_primary_stalls or args.trace_fast_path_stalls):
        raise ValueError('EEG CPU0 requires the uninstrumented asynchronous private replay')
    roles = replay_cpu_roles(args.split_worker_cpus, args.eeg_cpu0)
    if roles['parent'] is not None:
        if args.trace_stages or args.filter_backend != 'arm' or os.sched_getaffinity(0) != {0,1}:
            raise ValueError('Role affinity requires ARM replay with both CPUs initially allowed and no full tracing')
        os.sched_setaffinity(0, {0})
        live._telemetry_worker = functools.partial(replay_telemetry_worker,
            cpu=roles['background'], nice=args.background_nice)
        import mi_acquisition
        mi_acquisition._mi_worker = functools.partial(replay_mi_worker,
            cpu=roles['background'], nice=args.background_nice)
    array_stream_class=None
    if args.array_covariance_source and not args.array_covariance:
        raise ValueError('Array source requires explicit candidate opt-in')
    if args.array_covariance:
        array_stream_class=live.CovarianceFeatureStream
        if args.array_covariance_source:
            path=args.array_covariance_source.resolve()
            if path.parent!=Path(__file__).resolve().parent:
                raise ValueError('Array source must be in the private harness directory')
            spec=importlib.util.spec_from_file_location('private_array_covariance',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            array_stream_class=module.CovarianceFeatureStream
        if 'storage' not in inspect.signature(array_stream_class).parameters:
            raise ValueError('This release lacks the array API; refuse to silently disable emotion')
    if args.filter_backend == 'pl':
        if not Path('/dev/guardianloop_dma_keeper').is_char_device():
            raise RuntimeError('PL replay requires the staged kernel DMA owner')
        state = subprocess.run(['systemctl', 'is-active', 'guardianloop-cyton.service'],
                               capture_output=True, text=True, check=False).stdout.strip()
        if state != 'inactive':
            raise RuntimeError(f'Live Cyton service must be inactive, got {state!r}')
    if args.reader_fault_after is not None and not 0 < args.reader_fault_after < args.seconds*250:
        raise ValueError('Fault position must be inside the replay')
    n = args.seconds * 250
    if args.pause_at is not None and not (0 < args.pause_at < n and args.pause_at % 10 == 0
                                            and 0 < args.pause_seconds <= 5):
        raise ValueError('Pause must be at a 10-sample boundary with duration (0,5] s')
    if (args.rail_from is None) != (args.rail_to is None):
        raise ValueError('Both rail interval endpoints are required')
    if args.rail_from is not None and not (0 <= args.rail_from < args.rail_to <= n):
        raise ValueError('Invalid rail interval')
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    primary_dir = out
    if args.volatile_primary_dir:
        primary_dir = Path(args.volatile_primary_dir).resolve()
        if Path('/dev/shm') not in primary_dir.parents:
            raise ValueError('Replay volatile output must be below /dev/shm')
        primary_dir.mkdir(exist_ok=False)
    shadow_dir = out
    if args.volatile_shadow_dir:
        shadow_dir = Path(args.volatile_shadow_dir).resolve()
        if Path('/dev/shm') not in shadow_dir.parents:
            raise ValueError('Replay volatile shadow output must be below /dev/shm')
        shadow_dir.mkdir(exist_ok=False)
    shadow_path = shadow_dir/'shadow.json'
    seed_audit_path = shadow_dir/'shadow.events.jsonl' if args.audit_seed_candidate else None
    ssvep_path = shadow_dir/'ssvep.json'
    trace = None
    web_trace = None
    if args.trace_stages:
        from replay_stage_trace import install, StageTrace, traced_telemetry_worker
        trace = install(live, SeedShadow, TrialRecorder)
        web_trace = StageTrace()
        web_trace.wrap(TelemetryResponseCache, 'body', 'web_response_cache')
        live._telemetry_worker_original = live._telemetry_worker
        live._telemetry_worker = functools.partial(
            traced_telemetry_worker, destination=out/'telemetry_stages.json')
    elif args.trace_primary_stalls:
        from replay_stage_trace import install_primary
        trace = install_primary(live, array_stream_class or live.CovarianceFeatureStream, TrialRecorder)
    elif args.trace_fast_path_stalls:
        from replay_stage_trace import install_fast_path
        trace = install_fast_path(live, detailed_submit=args.trace_primary_submit)
    if args.without_telemetry:
        from replay_stage_trace import NoTelemetryWriter
        live.TelemetryWriter = NoTelemetryWriter
    if args.array_covariance:
        live.CovarianceFeatureStream = array_covariance_factory(array_stream_class)
    with np.load(args.input) as data:
        values = np.rint(data[args.input_kind]/live.DEFAULT_UV_PER_COUNT).astype(np.int64)
        original_seq = data[args.input_kind+'_seq'].astype(int)
    if args.force_rail:
        values[:, 6:8] = (2**23-1)
    frames = []
    for row in values:
        frame = bytearray([0xA0, 0])
        for v in row:
            frame.extend((int(v)&0xffffff).to_bytes(3,'big'))
        frame.extend(bytes(6)); frame.append(0xC0)
        frames.append(frame)
    read_fd, write_fd = os.pipe()
    go = multiprocessing.Event()

    def producer():
        go.wait()
        start = time.monotonic()
        maximum_late = 0.
        late_batches = 0
        pause_offset = 0.
        seq = int(original_seq[0])-1
        for first in range(0,n,10):
            if first == args.pause_at:
                time.sleep(args.pause_seconds)
                pause_offset += args.pause_seconds
            target = start+(first+10)/250+pause_offset
            time.sleep(max(0.,target-time.monotonic()))
            late = max(0.,time.monotonic()-target)
            maximum_late = max(maximum_late,late)
            late_batches += int(late>.1)
            block = bytearray()
            for i in range(first,min(first+10,n)):
                k = i%len(frames)
                delta = ((int(original_seq[k])-int(original_seq[k-1]))%256) if k else 1
                seq = (seq+delta)%256
                frame = bytearray(frames[k]); frame[1] = seq
                if args.rail_from is not None and args.rail_from <= i < args.rail_to:
                    for channel in (6, 7):
                        offset = 2 + 3*channel
                        frame[offset:offset+3] = (2**23-1).to_bytes(3, 'big')
                block.extend(frame)
            view = memoryview(block)
            while len(view):
                view = view[os.write(write_fd,view):]
        atomic_json(out/'producer.json', {'packets':n, 'elapsed_seconds':time.monotonic()-start,
                    'input_kind':args.input_kind, 'pause_at':args.pause_at,
                    'pause_seconds':args.pause_seconds, 'rail_from':args.rail_from,
                    'rail_to':args.rail_to,
                    'max_deadline_lateness_seconds':maximum_late,'batches_over_100ms':late_batches})
        os.close(write_fd)

    feeder = multiprocessing.Process(target=producer, name='replay-pipe-producer')
    feeder.start()
    os.close(write_fd)
    real_packets = live.packets
    consumed = [0]
    packet_compute = []
    packet_ages = []
    slow_packets = []
    primary_results = []
    original_result = live.publish_result
    def capture_result(value, calibrated, *a, **kw):
        marked = dict(value, source='offline_replay_not_live', real=False, offline=True)
        primary_results.append({'result':marked, 'calibrated':calibrated})
        return original_result(value, calibrated, *a, **kw)
    live.publish_result = capture_result
    def paced_packets(fd, timeout, with_timing=False, on_idle=None, **reader_options):
        reader = real_packets(read_fd, timeout, with_timing, on_idle, **reader_options)
        go.set()
        try:
            for item in reader:
                stamp = time.perf_counter()
                cpu = time.thread_time() if trace else 0.
                age = max(0., time.monotonic()-item[2])
                packet_ages.append(age)
                if trace:
                    trace.packet_index = consumed[0]
                yield item
                elapsed = time.perf_counter()-stamp
                packet_compute.append(elapsed)
                if trace and elapsed >= .050:
                    slow_packets.append(dict(packet=consumed[0], start_monotonic=stamp,
                        wall_ms=elapsed*1000, thread_cpu_ms=(time.thread_time()-cpu)*1000,
                        input_age_ms=age*1000))
                consumed[0] += 1
                if consumed[0] == args.reader_fault_after:
                    raise live.CytonReaderError(dict(kind=args.reader_fault_kind,
                        errno=5 if args.reader_fault_kind=='serial_io_error' else None,
                        exception='InjectedReplayFault', reads=0, bytes_read=0,
                        packets_queued=consumed[0], malformed_pending=0,
                        injected_replay_only=True))
                if consumed[0] == n:
                    break
        finally:
            reader.close()
    live.packets = paced_packets
    live.configure_serial = lambda fd: None
    live.write_command = lambda fd, command: None
    live.configure_eeg_channels = lambda fd: None
    live.termios.tcflush = lambda fd, mode: None
    def forbid_pl():
        raise AssertionError('The unrelated historical PL fatigue engine is forbidden in replay')
    live.GuardianLoopPynq = forbid_pl
    original_dumps = json.dumps
    def marked_dumps(payload, *a, **kw):
        if isinstance(payload,dict) and payload.get('source') in ('cyton_usb','bci'):
            payload = dict(payload,source='offline_replay_not_live',real=False,offline=True)
        return original_dumps(payload,*a,**kw)
    live.json.dumps = marked_dumps
    if args.async_seed_candidate:
        from async_seed_candidate import AsyncSeedShadow
        live.SeedShadow = lambda model, channels: AsyncSeedShadow(
            model, channels, status_path=shadow_path, audit_path=seed_audit_path,
            page_policy_path=args.page_policy_file)
    else:
        if args.audit_seed_candidate:
            from audited_seed_shadow import AuditedSeedShadow
            live.SeedShadow = lambda model, channels: AuditedSeedShadow(
                model, channels, status_path=shadow_path, audit_path=seed_audit_path)
        else:
            live.SeedShadow = lambda model, channels: SeedShadow(
                model, channels, source='replay', status_path=shadow_path)
    def isolated_recorder(channels, scale):
        recorder = TrialRecorder(channels, scale, control_path=out/'absent-command.json',
                                status_path=out/'recorder.json', record_root=out/'recordings')
        if args.record_raw:
            recorder.start(dict(trial_id='0000000000000001', task='ssvep',
                condition='ssvep_cued_diagnostic', phase='ssvep_diagnostic',
                participant_id='OFFLINE_REPLAY_NOT_NEW_HUMAN_DATA',
                protocol={'source':'offline_replay_not_live', 'control_enabled':False}),
                dict(packets_seen=0, sequence_gaps=0, malformed_bytes=0, dropped_packets=0))
            recorder.active['metadata']['stream_first_index'] = 0
            recorder.active['metadata']['label_provenance'] = 'Offline replay of saved EEG, not new human data or visual cues'
            atomic_json(recorder.active['directory']/'metadata.json', recorder.active['metadata'])
        return recorder
    live.TrialRecorder = isolated_recorder
    live.RECORDING_STATUS_PATH = out/'recorder.json'
    if args.page_policy_file and not args.async_seed_candidate:
        from page_scheduled_replay import ScheduledLane
        seed_factory=live.SeedShadow
        live.SeedShadow=lambda *a,**kw: ScheduledLane(seed_factory(*a,**kw),args.page_policy_file,'seed_candidate')
    if hasattr(live, 'SSVEPReaderRuntime'):
        import ssvep_acquisition
        ssvep_acquisition._worker = functools.partial(replay_ssvep_worker,
            page_policy_file=args.page_policy_file,cpu=roles['background'],
            nice=args.background_nice)
        runtime_class = live.SSVEPReaderRuntime
        class RecordedSSVEPReader(runtime_class):
            def close(self):
                super().close()
                final=json.loads(self.path.read_text())
                final.update(source='offline_replay_not_live', real=False, offline=True)
                atomic_json(self.path,final)
        def isolated_ssvep(*arguments, **options):
            options.update(status_path=ssvep_path, log_path=out/'cue.events.jsonl',
                           record_status_path=out/'recorder.json', port=0)
            runtime=RecordedSSVEPReader(*arguments, **options)
            if args.page_policy_file:
                from page_scheduled_replay import ScheduledSink
                runtime.reader_sink=ScheduledSink(runtime.reader_sink,args.page_policy_file,'ssvep_candidate')
            return runtime
        live.SSVEPReaderRuntime = isolated_ssvep
        live.SSVEP_PATH = out/'ssvep-error.json'
    else:
        cue_class = live.SSVEPCueRuntime
        live.SSVEPCueRuntime = lambda record_status_path: cue_class(
            log_path=out/'cue.events.jsonl', port=0, record_status_path=out/'recorder.json')
    live.LIVE_PATH = out/'shadow-error.json'
    if args.mi_tap_batch_candidate:
        import mi_acquisition
        mi_acquisition.MICandidateRuntime = functools.partial(mi_acquisition.MICandidateRuntime,
                                                             reader_batch_samples=10)
    if hasattr(live, 'SSVEPShadow'):
        ssvep_class = live.SSVEPShadow
        live.SSVEPShadow = lambda config, sos, channels, event_sink=None: ssvep_class(
            config, sos, channels, source='replay', status_path=ssvep_path,
            event_sink=event_sink)
        live.SSVEP_PATH = out/'ssvep-error.json'
    sys.argv = ['isolated-soak','--port','/dev/null','--esp32-url','',
                '--status-file',str(primary_dir/'status.json'),'--telemetry-file',str(primary_dir/'telemetry.json')]
    if args.async_primary_candidate:
        sys.argv.extend(['--isolated-primary-worker', '--primary-worker-cpus', roles['primary']])
    if args.reader_batch_candidate:
        sys.argv.append('--isolated-reader-batch')
    if args.filter_backend == 'pl':
        sys.argv.extend(['--filter-backend', 'pl', '--filter-batch-samples', '10'])
    if args.allow_experimental_mi != bool(args.mi_experimental_model):
        raise ValueError('MI model and explicit opt-in required together')
    if args.allow_experimental_mi:
        sys.argv.extend(['--mi-experimental-model',str(args.mi_experimental_model),
                        '--allow-experimental-mi','--mi-source','replay',
                        '--mi-web-port',str(args.mi_web_port),'--mi-audit-log',str(out/'mi-events.jsonl')])
    stop = threading.Event()
    cache = TelemetryResponseCache(primary_dir/'telemetry.json')
    failures = []
    monitor_rows = [0]
    started = time.monotonic()
    def monitor():
        with (out/'monitor.jsonl').open('w') as log:
            while not stop.wait(1):
                try:
                    response = json.loads(cache.body())
                    t = response['telemetry']
                    if t:
                        assert t['source']=='offline_replay_not_live' and t['real'] is False
                    row = {'elapsed_seconds':time.monotonic()-started,
                           'snapshot_age_seconds':response.get('snapshot_age_seconds'),
                           'stale':response['stale'], 'packets_seen':t.get('packets_seen'),
                           'runtime':t.get('runtime'), 'parent':process_stats(os.getpid()),
                           'children':[dict(process_stats(c.pid) or {},name=c.name)
                                       for c in multiprocessing.active_children()]}
                    status_path = primary_dir/'status.json'
                    if status_path.exists():
                        status = json.loads(status_path.read_text())
                        emotion = status.get('emotion') or {}
                        row['primary'] = {'state':status.get('state'),
                                          'valid':status.get('valid'),
                                          'reason':status.get('reason'),
                                          'emotion_state':emotion.get('state'),
                                          'emotion_valid':emotion.get('valid'),
                                          'source':status.get('source')}
                    if ssvep_path.exists():
                        row['ssvep'] = json.loads(ssvep_path.read_text())
                    if shadow_path.exists():
                        row['seed'] = json.loads(shadow_path.read_text())
                    log.write(json.dumps(row)+'\n'); log.flush()
                    monitor_rows[0] += 1
                except Exception as exc:
                    failures.append(repr(exc))
                    stop.set()
    observer = threading.Thread(target=monitor,daemon=True)
    cpu_start = time.process_time()
    child_start = resource.getrusage(resource.RUSAGE_CHILDREN)
    observer.start()
    error = None
    try:
        with (out/'offline-replay.log').open('w') as log:
            destination = log
            if args.trace_fast_path_stalls:
                from replay_stage_trace import TracedReplayLog
                destination = TracedReplayLog(log, trace)
            with contextlib.redirect_stdout(destination):
                print('OFFLINE_PACED_PIPE_REPLAY_ONLY; not new human data. '
                      f'input_repeated={n > len(frames)}; filter_backend={args.filter_backend}',flush=True)
                live.main()
    except Exception as exc:
        error = repr(exc)
        raise
    finally:
        stop.set(); observer.join(timeout=3)
        feeder.join(timeout=3)
        if feeder.is_alive():
            feeder.terminate(); feeder.join(timeout=2)
        os.close(read_fd)
        child_end = resource.getrusage(resource.RUSAGE_CHILDREN)
        atomic_json(out/'primary_results.json', primary_results)
        if args.trace_stages:
            trace.save(out/'stages.json')
            web_trace.save(out/'web_stages.json')
            atomic_json(out/'slow_packets.json', slow_packets)
        elif args.trace_primary_stalls or args.trace_fast_path_stalls:
            trace.save(out/'primary_stalls.json')
            atomic_json(out/'slow_packets.json', slow_packets)
        atomic_json(out/'report.json', {'requested_seconds':args.seconds,'wall_seconds':time.monotonic()-started,
                    'stage_instrumentation':args.trace_stages,
                    'primary_stall_instrumentation':args.trace_primary_stalls,
                    'fast_path_stall_instrumentation':args.trace_fast_path_stalls,
                    'submission_stall_instrumentation':args.trace_primary_submit,
                    'array_covariance_candidate':args.array_covariance,
                    'page_policy_file':str(args.page_policy_file) if args.page_policy_file else None,
                    'input_repeated':n > len(frames),
                    'raw_recording_enabled':args.record_raw,
                    'async_seed_candidate':args.async_seed_candidate,
                    'async_primary_candidate':args.async_primary_candidate,
                    'reader_batch_candidate':args.reader_batch_candidate,
                    'mi_tap_batch_candidate':args.mi_tap_batch_candidate,
                    'audit_seed_candidate':args.audit_seed_candidate,
                    'telemetry_disabled_diagnostic':args.without_telemetry,
                    'mi_runtime_enabled':args.allow_experimental_mi,
                    'process_cpu_affinity':sorted(os.sched_getaffinity(0)),
                    'split_worker_cpus_diagnostic':args.split_worker_cpus,
                    'eeg_cpu0_diagnostic':args.eeg_cpu0,
                    'replay_cpu_roles':roles,
                    'background_nice_diagnostic':args.background_nice,
                    'process_nice':os.getpriority(os.PRIO_PROCESS,0),
                    'synthetic_rail_diagnostic':args.force_rail,
                    'input_kind':args.input_kind,
                    'filter_backend':args.filter_backend,
                    'pause_at':args.pause_at, 'pause_seconds':args.pause_seconds,
                    'rail_from':args.rail_from, 'rail_to':args.rail_to,
                    'injected_reader_fault_after':args.reader_fault_after,
                    'primary_status_directory':str(primary_dir),
                    'shadow_status_directory':str(shadow_dir),
                    'packet_input_age_p95_ms':float(np.quantile(packet_ages,.95)*1000) if packet_ages else None,
                    'packet_input_age_max_ms':float(max(packet_ages)*1000) if packet_ages else None,
                    'packets_consumed':consumed[0], 'packets_expected':n,
                    'parent_cpu_seconds':time.process_time()-cpu_start,
                    'children_cpu_seconds':child_end.ru_utime+child_end.ru_stime-child_start.ru_utime-child_start.ru_stime,
                    'parent_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    'packet_compute_p95_ms':float(np.quantile(packet_compute,.95)*1000) if packet_compute else None,
                    'packet_compute_p99_ms':float(np.quantile(packet_compute,.99)*1000) if packet_compute else None,
                    'packet_compute_max_ms':float(max(packet_compute)*1000) if packet_compute else None,
                    'monitor_rows':monitor_rows[0], 'monitor_errors':failures,'error':error,
                    'remaining_children':[c.name for c in multiprocessing.active_children()],
                    'scope':'Paced replay through real pipe reader, repeated recorded trace, preserved within-trace counter gaps. '
                            'No real USB radio or new labeled EEG; PL filter is used only when explicitly selected. '
                            'Telemetry cache requested once/second, network/browser rendering excluded.'})


if __name__=='__main__':
    main()

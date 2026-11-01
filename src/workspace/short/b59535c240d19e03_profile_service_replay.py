"""Linux-only isolated replay through the actual deployed main loop, no USB/PL access."""
import argparse
from collections import defaultdict
import contextlib
import json
from pathlib import Path
import resource
import sys
import time
from types import SimpleNamespace

import numpy as np
import cyton_guardianloop as live
from cyton_trial_recorder import TrialRecorder
from seed_shadow import SeedShadow


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--repeats', type=int, default=1)
    args = p.parse_args()
    out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=True)
    clock = [0.]
    live.time = SimpleNamespace(monotonic=lambda: clock[0], time=time.time, sleep=lambda _: None)
    live.configure_serial = lambda fd: None
    live.write_command = lambda fd, cmd: None
    live.configure_eeg_channels = lambda fd: None
    live.termios.tcflush = lambda fd, mode: None
    # The fixed montage must never construct the unrelated historical PL engine.
    def forbid_pl():
        raise AssertionError('Unexpected PL construction during ARM replay')
    live.GuardianLoopPynq = forbid_pl
    totals = []
    measured = defaultdict(lambda: {'calls':0, 'inclusive_s':0., 'exclusive_s':0., 'max_s':0.})
    stack = []
    def instrument(owner, attr, name):
        original = getattr(owner, attr)
        def wrapped(*a, **kw):
            label = name(a) if callable(name) else name
            frame = [time.perf_counter(), 0.]
            stack.append(frame)
            try:
                return original(*a, **kw)
            finally:
                elapsed = time.perf_counter() - frame[0]
                stack.pop()
                if stack:
                    stack[-1][1] += elapsed
                item = measured[label]
                item['calls'] += 1
                item['inclusive_s'] += elapsed
                item['exclusive_s'] += elapsed - frame[1]
                item['max_s'] = max(item['max_s'], elapsed)
        setattr(owner, attr, wrapped)
    original_result = live.publish_result
    current = [out]
    primary_results = []
    original_dumps = json.dumps
    def marked_dumps(payload, *a, **kw):
        if isinstance(payload, dict) and payload.get('source') in ('cyton_usb', 'bci'):
            payload = dict(payload, source='offline_replay_not_live', real=False)
        return original_dumps(payload, *a, **kw)
    # Mark at serialization, without extra disk reads/writes in the timed path.
    live.json.dumps = marked_dumps
    def result(value, calibrated, path, esp32_url, **kwargs):
        assert not esp32_url
        primary_results.append({'result':value, 'calibrated':calibrated})
        original_result(value, calibrated, path, '', **kwargs)
    live.publish_result = result
    live.SeedShadow = lambda model, channels: SeedShadow(model, channels, source='replay',
                                                        status_path=current[0] / 'shadow.json')
    live.TrialRecorder = lambda channels, scale: TrialRecorder(
        channels, scale, control_path=current[0]/'absent-command.json',
        status_path=current[0]/'recorder.json', record_root=current[0]/'recordings')
    live.LIVE_PATH = out / 'shadow-error.json'
    if hasattr(live, 'SSVEPShadow'):
        ssvep_class = live.SSVEPShadow
        live.SSVEPShadow = lambda config, sos, channels: ssvep_class(
            config, sos, channels, source='replay', status_path=current[0]/'ssvep.json')
        live.SSVEP_PATH = out/'ssvep-error.json'
        instrument(ssvep_class, 'packet', 'ssvep_packet')
    instrument(live.CausalEEGFilter, 'process', lambda a: 'filter_single' if len(a[1]) == 1 else 'filter_block')
    instrument(live.CytonSQIMonitor, 'process', 'sqi')
    instrument(live.CovarianceFeatureStream, 'append', 'emotion_band_filters')
    instrument(live.CovarianceFeatureStream, 'feature', 'emotion_feature')
    instrument(live.CovarianceSVM, 'predict_feature', 'emotion_svm')
    instrument(live.FourChannelFatigue, 'append', 'fatigue_bands')
    instrument(live.FourChannelFatigue, 'process_window', 'fatigue_window')
    instrument(SeedShadow, 'packet', 'seed_packet')
    instrument(live, 'publish_telemetry', 'telemetry_json')
    instrument(live, 'publish_result', 'result_json')
    instrument(live, 'decode_eeg_counts', 'packet_decode')
    instrument(TrialRecorder, 'poll', 'recorder_poll')
    if hasattr(live, 'TelemetryWriter'):
        instrument(live.TelemetryWriter, 'submit', 'telemetry_enqueue')
    with np.load(args.input) as data:
        for case in ('recorded', 'synthetic'):
            counts = np.rint(data[case] / live.DEFAULT_UV_PER_COUNT).astype(np.int64)
            assert np.max(np.abs(counts)) < 2**23
            frames = []
            for row, seq in zip(counts, data[case + '_seq']):
                frame = bytearray([0xA0, int(seq)])
                for value in row:
                    frame.extend((int(value) & 0xffffff).to_bytes(3, 'big'))
                frame.extend(bytes(6)); frame.append(0xC0)
                assert len(frame) == 33
                frames.append(bytes(frame))
            def packets(fd, timeout, with_timing=False, on_idle=None):
                assert with_timing
                backlog = 0.
                for i, frame in enumerate(frames):
                    clock[0] = i / 250
                    stamp = time.perf_counter()
                    yield frame, 0, clock[0]
                    duration = time.perf_counter() - stamp
                    backlog = max(0., backlog + duration - .004)
                    packet_times.append(duration)
                    queue_delays.append(backlog)
            live.packets = packets
            for repeat in range(args.repeats):
                directory = out / (case + '_' + str(repeat)); directory.mkdir(exist_ok=True)
                current[0] = directory; clock[0] = 0.
                measured.clear()
                primary_results.clear()
                packet_times = []
                queue_delays = []
                sys.argv = ['isolated-replay', '--port', '/dev/null', '--esp32-url', '',
                            '--channel-map', ','.join(live.DEFAULT_CHANNEL_MAP),
                            '--status-file', str(directory/'status.json'),
                            '--telemetry-file', str(directory/'telemetry.json')]
                start = time.perf_counter(); cpu = time.process_time()
                child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
                with (directory/'offline-replay.log').open('w') as log, contextlib.redirect_stdout(log):
                    print('OFFLINE_REPLAY_ONLY: no live serial, no PL, no public web status writes.')
                    live.main()
                children = resource.getrusage(resource.RUSAGE_CHILDREN)
                (directory/'primary_results.json').write_text(json.dumps(primary_results), encoding='utf-8')
                totals.append({'case':case, 'repeat':repeat, 'input_seconds':len(frames)/250,
                               'wall_s':time.perf_counter()-start, 'cpu_s':time.process_time()-cpu,
                               'rss_peak_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                               'children_cpu_s':children.ru_utime + children.ru_stime - child_before.ru_utime - child_before.ru_stime,
                               'children_peak_rss_kib':children.ru_maxrss,
                               'packet_compute_p95_ms':float(np.quantile(packet_times,.95)*1000),
                               'packet_compute_max_ms':float(max(packet_times)*1000),
                               'simulated_queue_delay_max_ms':float(max(queue_delays)*1000),
                               'simulated_queue_delay_final_ms':float(queue_delays[-1]*1000),
                               'simulated_queue_delay_p95_ms':float(np.quantile(queue_delays,.95)*1000),
                               'last_60s_compute_seconds':float(sum(packet_times[-15000:])),
                               'stages': dict(measured)})
                np.savez_compressed(directory/'packet_timing.npz', compute_seconds=packet_times,
                                    simulated_queue_delay_seconds=queue_delays)
                print(totals[-1], flush=True)
                (out/'report.json').write_text(json.dumps({'runs':totals,
                    'scope':'Actual main loop; fake packet generator at virtual timestamps; real local replay JSON/log writes. '
                    'Serial configuration/reader/wait bypassed, no actual PL. Replay source marking adds no extra disk writes. '
                    'Method timers add overhead; exclusive times subtract nested instrumented calls. '
                    'Queue delay is a deterministic 250Hz producer simulation, not observed USB queue occupancy. '
                    'Browser/network delivery excluded; unchanged production services remain active.'},indent=2))


if __name__ == '__main__':
    main()

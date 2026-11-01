"""Private service lifecycle rehearsal; /dev/null and generated input only."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from async_primary import AsyncPrimaryWorker
from calibration_session import CalibrationSession
import cyton_guardianloop as live
from cyton_sqi import CausalEEGFilter
from cyton_trial_recorder import atomic_json
from test_async_primary import processor, counters
from test_calibration_main import generated_signal
from wear_session import WearSession


def checkpoint_context(directory):
    model = Path(__file__).with_name('cyton_fatigue_overlap4.json')
    context = CalibrationSession.context_for('/dev/null', live.DEFAULT_CHANNEL_MAP,
        live.DEFAULT_UV_PER_COUNT, (model, Path(__file__).with_name('gameemo_covariance_svm.npz'),
        Path(directory) / 'no-legacy-model'), 'arm')
    context['wear_id'] = WearSession(directory).initialize()
    return context


def complete(directory):
    engine = processor()
    session = CalibrationSession(directory / 'calibration-session.json', checkpoint_context(directory))
    if not session.load(engine.sqi_monitor, engine.four_channel_fatigue):
        raise RuntimeError('The preceding partial checkpoint was not restored')
    engine.reset_stream()
    before = engine.calibration_progress
    raw = generated_signal((16 - before) * 2000, 88)
    clean = CausalEEGFilter().process(raw)
    worker = AsyncPrimaryWorker(engine, calibration_session=session)
    try:
        for first in range(0, len(raw), 2000):
            stamp = time.monotonic()
            worker.submit(raw[first:first+2000] / engine.scale, clean[first:first+2000],
                np.zeros(2000, dtype=bool), counters(first+2000), stamp)
            deadline = stamp + 10
            while worker.progress[3] < stamp and time.monotonic() < deadline:
                worker.poll()
                time.sleep(.003)
            if worker.progress[3] < stamp:
                raise TimeoutError('Private completion worker failed to drain')
        if worker.calibration_progress != 15 or not worker.calibration_ready:
            raise RuntimeError('Private completion did not produce a full baseline')
        return dict(initial_calibration=before, final_calibration=worker.calibration_progress,
            checkpoint_write_failures=worker.checkpoint_write_failures, worker_pid=worker.process.pid)
    finally:
        worker.close()


def main_probe(directory, phase):
    count = dict(partial=6000, crash=6000, restored=8000, newwear=6000, rejected=200)[phase]
    values = np.rint(generated_signal(count, 87) / live.DEFAULT_UV_PER_COUNT).astype(int)
    results, workers, submissions, opened = [], [], [], []
    original_worker, original_publish, original_open = AsyncPrimaryWorker, live.publish_result, os.open
    def factory(*args, **kwargs):
        worker = original_worker(*args, **kwargs)
        submit = worker.submit
        def tracked(*arguments):
            result = submit(*arguments)
            if not result:
                raise RuntimeError('Functional rehearsal must not lose an input batch')
            submissions[:] = [(worker.generation[0], arguments[-1])]
            return result
        worker.submit = tracked
        workers.append(worker)
        return worker
    def drain():
        if not submissions:
            return
        epoch, stamp = submissions[0]
        worker = workers[0]
        deadline = time.monotonic() + 10
        while worker.generation[0] == epoch and worker.progress[3] < stamp:
            worker.check_alive()
            if time.monotonic() > deadline:
                raise TimeoutError('Private service worker did not drain')
            time.sleep(.001)
    def frames(*args, **kwargs):
        for index, row in enumerate(values):
            drain()  # Functional backpressure, not a throughput qualification.
            crash_target = results[0]['calibration_current'] + 1
            if phase == 'crash' and workers[0].calibration_progress >= crash_target:
                saved = json.loads((directory / 'calibration-session.json').read_text())
                if len(saved['fatigue']['baseline']) < crash_target:
                    raise RuntimeError('Cannot crash before the partial checkpoint commits')
                atomic_json(directory / 'crash-marker.json', dict(pid=os.getpid(),
                    worker_pid=workers[0].process.pid, initial_calibration=results[0]['calibration_current'],
                    final_calibration=len(saved['fatigue']['baseline']), source='generated_private_rehearsal'))
                os.kill(os.getpid(), signal.SIGKILL)
            if phase == 'restored' and index == 1000:
                time.sleep(.55)
                kwargs['on_idle'](time.monotonic())
            if phase == 'newwear' and index == 500:
                wear = WearSession(directory)
                wear.request_new(wear.snapshot()['id'])
                kwargs['on_idle'](time.monotonic())
            body = b''.join((int(v) & 0xFFFFFF).to_bytes(3, 'big') for v in row)
            yield bytes((0xA0, index % 256)) + body + bytes(6) + bytes((0xC0,)), 0, time.monotonic()
        drain()
        time.sleep(.025)
        kwargs['on_idle'](time.monotonic())
    def publish(row, *args, **kwargs):
        row = dict(row, source='offline_recovery_test', real=False, offline=True)
        results.append(json.loads(json.dumps(row)))
        return original_publish(row, *args, **kwargs)
    def open_null(path, *args, **kwargs):
        if path != '/dev/null':
            raise AssertionError('Hardware open forbidden in this recovery rehearsal: ' + str(path))
        opened.append(path)
        return original_open(path, *args, **kwargs)
    if phase == 'rejected':
        path = directory / 'calibration-session.json'
        corrupted = json.loads(path.read_text())
        corrupted['sqi']['scale'][0][0] = -1
        path.write_text(json.dumps(corrupted))
    with contextlib.ExitStack() as stack:
        for name in ('configure_serial', 'configure_eeg_channels', 'write_command'):
            stack.enter_context(patch.object(live, name))
        stack.enter_context(patch.object(live.termios, 'tcflush'))
        stack.enter_context(patch.object(live, 'SeedShadow', return_value=None))
        stack.enter_context(patch.object(live, 'SSVEPReaderRuntime', return_value=None))
        stack.enter_context(patch.object(live, 'TelemetryWriter'))
        recorder = stack.enter_context(patch.object(live, 'TrialRecorder')).return_value
        recorder.active = None
        stack.enter_context(patch.object(live, 'GuardianLoopPynq', side_effect=AssertionError('PL forbidden')))
        stack.enter_context(patch.object(live, 'KernelOwnedCausalFilter', side_effect=AssertionError('PL forbidden')))
        stack.enter_context(patch.object(live, 'packets', side_effect=frames))
        stack.enter_context(patch.object(live, 'publish_result', side_effect=publish))
        guarded_os = SimpleNamespace(**vars(os))
        guarded_os.open = open_null
        stack.enter_context(patch.object(live, 'os', guarded_os))
        stack.enter_context(patch('async_primary.AsyncPrimaryWorker', side_effect=factory))
        stack.enter_context(patch.dict(os.environ, {'GL_SEED_EXECUTION':'sync','GL_COVARIANCE_STORAGE':'array'}))
        stack.enter_context(patch.object(sys, 'argv', ['private-service', '--port', '/dev/null',
            '--esp32-url', '', '--isolated-primary-worker', '--isolated-primary-checkpoint',
            '--emotion-model', str(directory / 'no-legacy-model'),
            '--status-file', str(directory / 'status.json'),
            '--telemetry-file', str(directory / 'telemetry.json')]))
        live.main()
    checkpoint = json.loads((directory / 'calibration-session.json').read_text())
    if phase == 'crash':
        raise RuntimeError('Crash rehearsal ended without reaching a newly committed checkpoint')
    result = dict(initial_calibration=results[0]['calibration_current'],
        final_calibration=workers[0].calibration_progress, raw_usb_opened=False, opened=opened,
        worker_pid=workers[0].process.pid, checkpoint_write_failures=workers[0].checkpoint_write_failures,
        checkpoint_calibration=len(checkpoint['fatigue']['baseline']),
        checkpoint_matches_wear=checkpoint['context']['wear_id'] == WearSession(directory).snapshot()['id'],
        reports=results, input_samples=count)
    if (results[0].get('valid') is not False or results[-1].get('valid') is not False
            or results[-1]['emotion'].get('valid') is not False):
        raise RuntimeError('Startup or EOF restored an old valid prediction')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--phase', choices=('partial','crash','complete','restored','newwear','rejected'), required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.parent != Path('/dev/shm') or not directory.name.startswith('gl-primary-recovery-'):
        raise ValueError('Recovery probe must remain in its separate tmpfs directory')
    destination = directory / (args.phase + '-report.json')
    if destination.exists():
        raise ValueError('Do not overwrite earlier recovery evidence')
    started = time.monotonic()
    value = complete(directory) if args.phase == 'complete' else main_probe(directory, args.phase)
    value.update(phase=args.phase, pid=os.getpid(), elapsed_seconds=time.monotonic()-started,
        scope='Generated input and private service restart; no radio or accuracy/timing qualification')
    atomic_json(destination, value)
    print('PRIVATE_RECOVERY_PHASE_COMPLETE:' + args.phase, flush=True)


if __name__ == '__main__':
    main()

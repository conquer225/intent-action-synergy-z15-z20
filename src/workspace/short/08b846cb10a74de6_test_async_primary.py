"""Recorded arithmetic/state tests; no USB, PL, or physical outputs."""
import importlib.util
import os
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock

import numpy as np

from cyton_covariance import CovarianceFeatureStream, CovarianceSVM
from cyton_fatigue import FourChannelFatigue
from cyton_sqi import CausalEEGFilter, CytonSQIMonitor, primary_windows, segmented_sqi
from primary_window import PrimaryWindowProcessor
from test_primary_stream_recovery import FATIGUE_MODEL, CAP
from test_calibration_main import generated_signal


def processor():
    path = Path(__file__).with_name('gameemo_covariance_svm.npz')
    return PrimaryWindowProcessor(CytonSQIMonitor(), FourChannelFatigue(FATIGUE_MODEL),
        CovarianceSVM(path), CovarianceFeatureStream(CAP, storage='array'), None,
        None, None, CAP, 4_500_000./24./(2**23-1), 'arm', primary_windows, segmented_sqi)


def counters(count):
    return dict(packets_seen=count, dropped_packets=0, sequence_gaps=0,
                unresolved_gaps=0, malformed_bytes=0)


class BlockingProcessor:
    engine = None
    filter_backend = 'arm'
    calibration_progress = 15
    calibration_ready = True

    def __init__(self, started, release):
        self.started, self.release = started, release
        self.sqi_monitor = SimpleNamespace(calibrated_channels=np.ones(8, dtype=bool))

    def append(self, raw, filtered, broken, counters):
        self.started.set()
        if not self.release.wait(timeout=3):
            raise TimeoutError('Test gate not released')
        return dict(valid=True, state='NORMAL', raw=float(raw[0]))

    def reset_stream(self):
        pass

    def new_wearing(self):
        self.calibration_progress = 0
        self.calibration_ready = False


class PrimaryProcessorTests(unittest.TestCase):
    def test_completed_and_partial_calibration_retained_until_explicit_new_wear(self):
        engine = processor()
        raw = generated_signal(32000, 87)
        clean = CausalEEGFilter().process(raw)
        scale = engine.scale
        reports = []
        for index, (x, y) in enumerate(zip(raw, clean)):
            report = engine.append(x/scale, y, False, counters(index+1))
            if report:
                reports.append(report)
                if report['calibration_current'] == 1:
                    engine.reset_stream()
                    self.assertEqual(engine.calibration_progress, 1)
        self.assertEqual(engine.calibration_progress, 15)
        baseline = engine.four_channel_fatigue.mean.copy()
        engine.reset_stream()
        self.assertEqual(engine.calibration_progress, 15)
        np.testing.assert_array_equal(baseline, engine.four_channel_fatigue.mean)
        self.assertFalse(engine.covariance_stream.ready)
        self.assertIsNone(engine.last_fatigue_result)
        engine.new_wearing()
        self.assertEqual(engine.calibration_progress, 0)
        self.assertFalse(engine.calibration_ready)
        self.assertFalse(engine.sqi_monitor.calibrated_channels.any())


@unittest.skipUnless(os.name == 'posix', 'Worker requires Linux fork')
class AsyncPrimaryTests(unittest.TestCase):
    def test_compute_lag_withdraws_without_resetting_continuous_input(self):
        from test_calibration_main import CalibrationMainTests
        from cyton_sqi import CausalEEGFilter
        worker = Mock(calibration_progress=15, calibration_ready=True, identity={}, stats={})
        worker.lag.return_value = 1.
        worker.poll.return_value = []
        worker.submit.return_value = True
        reset = CausalEEGFilter.reset
        with tempfile.TemporaryDirectory() as directory:
            with patch('async_primary.AsyncPrimaryWorker', return_value=worker):
                with patch.object(CausalEEGFilter, 'reset', autospec=True, side_effect=reset) as resets:
                    rows = CalibrationMainTests().run_main(directory, 360, async_primary=True)
        withdrawn = [r for r in rows if r.get('reason') == 'PRIMARY_WORKER_BACKLOG']
        self.assertEqual(len(withdrawn), 1)
        self.assertFalse(withdrawn[0]['valid'])
        self.assertEqual(withdrawn[0]['calibration_current'], 15)
        self.assertEqual(resets.call_count, 1)  # Initial construction only.
        self.assertEqual(worker.invalidate.call_count, 1)  # EOF, not model lag.
        self.assertGreater(worker.submit.call_count, 20)
        self.assertLess(worker.poll.call_count, 90)  # Not one IPC poll per packet.

    def test_private_candidate_rejects_live_usb_pl_and_checkpoint_modes(self):
        import contextlib
        import io
        import sys
        import cyton_guardianloop as live
        cases = (['--port', '/dev/ttyUSB0'], ['--port', '/dev/null', '--wait-for-data'],
                 ['--port', '/dev/null', '--filter-backend', 'pl'],
                 ['--port', '/dev/null', '--esp32-url', 'http://invalid.local'])
        for flags in cases:
            with self.subTest(flags=flags), contextlib.redirect_stderr(io.StringIO()):
                with patch.object(sys, 'argv', ['candidate', '--isolated-primary-worker', *flags]):
                    with patch.object(live.os, 'open') as opened, self.assertRaises(SystemExit):
                        live.main()
                    opened.assert_not_called()

    def test_queue_full_is_bounded_and_inflight_old_epoch_cannot_return(self):
        import multiprocessing
        from async_primary import AsyncPrimaryWorker
        context = multiprocessing.get_context('fork')
        started, release = context.Event(), context.Event()
        worker = AsyncPrimaryWorker(BlockingProcessor(started, release), capacity=1)
        raw = np.ones((1,8))
        try:
            self.assertTrue(worker.submit(raw, raw, [False], counters(1), time.monotonic()))
            self.assertTrue(started.wait(timeout=1))
            self.assertTrue(worker.submit(raw, raw, [False], counters(2), time.monotonic()))
            before = time.monotonic()
            self.assertFalse(worker.submit(raw, raw, [False], counters(3), before))
            self.assertLess(time.monotonic()-before, .1)
            worker.invalidate()
            release.set()
            time.sleep(.1)
            self.assertEqual(worker.poll(), [])
            self.assertEqual(worker.calibration_progress, 15)
            raw[:] = 7
            self.assertTrue(worker.submit(raw, raw, [False], counters(4), time.monotonic()))
            raw[:] = 100
            deadline = time.monotonic()+1
            replies = []
            while not replies and time.monotonic() < deadline:
                replies = worker.poll()
                time.sleep(.005)
            self.assertEqual(replies[0]['result']['raw'], 7)
            self.assertGreaterEqual(replies[0]['compute_ms'], 0.)
            self.assertNotIn('compute_ms', replies[0]['result'])
        finally:
            release.set()
            worker.close()

    def test_sync_extraction_exactly_matches_original_full_main(self):
        reference = os.environ.get('GL_TEST_PRIMARY_REFERENCE')
        if not reference:
            self.skipTest('Pinned pre-refactor source required')
        import sys
        import cyton_guardianloop as live
        from test_calibration_main import CalibrationMainTests
        spec = importlib.util.spec_from_file_location('primary_reference', reference)
        original = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(original)
        results = []
        model = Path(__file__).with_name('gameemo_covariance_svm.npz')
        with patch.dict(os.environ, {'GL_COVARIANCE_STORAGE': 'array'}):
            for module in (original, live):
                with tempfile.TemporaryDirectory() as directory:
                    with patch.dict(sys.modules, {'cyton_guardianloop': module}):
                        results.append(CalibrationMainTests().run_main(directory, 39000,
                                                                      covariance_model=model))
        self.assertEqual(results[0], results[1])
        self.assertTrue(any(r.get('emotion', {}).get('state') == 'prediction' for r in results[1]))
        self.assertTrue(any(r.get('state') in ('NORMAL', 'MILD', 'SEVERE') for r in results[1]))

    def test_worker_preserves_all_postcalibration_numerical_results(self):
        from async_primary import AsyncPrimaryWorker
        reference, remote = processor(), processor()
        raw = generated_signal(36000, 88)
        clean = CausalEEGFilter().process(raw)
        counts = raw/reference.scale
        actual, expected = [], []
        worker = AsyncPrimaryWorker(remote)
        try:
            for end in range(2000, 36001, 2000):
                first = end-2000
                batch = counters(end)
                before = len(expected)
                for x, y in zip(counts[first:end], clean[first:end]):
                    result = reference.append(x, y, False, batch)
                    if result:
                        expected.append(result)
                self.assertTrue(worker.submit(counts[first:end], clean[first:end],
                                np.zeros(2000, dtype=bool), batch, time.monotonic()))
                deadline = time.monotonic()+5
                while len(actual) < len(expected) and time.monotonic() < deadline:
                    actual.extend(m['result'] for m in worker.poll(max_age=5))
                    time.sleep(.005)
                self.assertGreater(len(expected), before)
                self.assertEqual(len(actual), len(expected))
            self.assertEqual(actual, expected)
            self.assertEqual(worker.calibration_progress, 15)
            worker.invalidate()
            self.assertEqual(worker.calibration_progress, 15)
            worker.invalidate(new_wearing=True)
            self.assertEqual(worker.calibration_progress, 0)
            self.assertFalse(worker.calibration_ready)
        finally:
            worker.close()
        self.assertFalse(worker.process.is_alive())

    def test_age_epoch_and_new_wear_gates(self):
        from async_primary import AsyncPrimaryWorker
        worker = AsyncPrimaryWorker(processor())
        try:
            now = time.monotonic()
            for epoch, stamp in ((0, now-1), (0, now+1), (-1, now)):
                worker.replies.put(('result', dict(epoch=epoch, received_at=stamp,
                                                  result={'valid': True})))
            time.sleep(.03)
            self.assertEqual(worker.poll(now), [])
            self.assertEqual(worker.stats['stale_replies'], 2)
            self.assertEqual(worker.stats['old_epoch_replies'], 1)
            worker.replies.put(('result', dict(epoch=0, received_at=now,
                                              result={'valid': True})))
            worker.invalidate(new_wearing=True)
            time.sleep(.03)
            self.assertEqual(worker.poll(now), [])
            self.assertEqual(worker.stats['old_epoch_replies'], 2)
            worker.process.terminate()
            worker.process.join(timeout=2)
            with self.assertRaisesRegex(RuntimeError, 'exited'):
                worker.submit(np.zeros((10, 8)), np.zeros((10, 8)),
                              np.zeros(10), counters(10), now)
        finally:
            worker.close()


if __name__ == '__main__':
    unittest.main()

"""Real fork/checkpoint boundaries with generated signals; not a live timing test."""
import contextlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from calibration_session import CalibrationSession
from cyton_sqi import CausalEEGFilter
from test_async_primary import processor, counters
from test_calibration_main import generated_signal


@unittest.skipUnless(os.name == 'posix', 'Checkpoint worker requires Linux fork')
class AsyncCheckpointTests(unittest.TestCase):
    def setUp(self):
        from async_primary import AsyncPrimaryWorker
        self.worker_class = AsyncPrimaryWorker
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'calibration.json'
        self.context = dict(boot='test-boot', model='same-model', wear_id='a' * 32)

    def session(self):
        return CalibrationSession(self.path, dict(self.context))

    def feed(self, worker, raw, clean, scale):
        for first in range(0, len(raw), 2000):
            stamp = time.monotonic()
            end = first + 2000
            self.assertTrue(worker.submit(raw[first:end] / scale, clean[first:end],
                np.zeros(len(raw[first:end]), dtype=bool), counters(end), stamp))
            deadline = stamp + 8
            while worker.progress[3] < stamp and time.monotonic() < deadline:
                worker.poll()  # Preserve the normal 500 ms reply gate.
                time.sleep(.003)
            self.assertGreaterEqual(worker.progress[3], stamp)
            worker.poll()

    def seed(self, count):
        engine = processor()
        clean = CausalEEGFilter().process(generated_signal(count * 2000, 87))
        for window in clean.reshape(count, 2000, 8):
            engine.sqi_monitor.process(window)
            engine.four_channel_fatigue.append(window)
            engine.four_channel_fatigue.process_window(True, True)
        engine.reset_stream()
        session = self.session()
        session.save(engine.sqi_monitor, engine.four_channel_fatigue)
        return engine, session

    def restored(self):
        engine, session = processor(), self.session()
        self.assertTrue(session.load(engine.sqi_monitor, engine.four_channel_fatigue))
        engine.reset_stream()
        self.assertIsNone(engine.last_fatigue_result)
        self.assertIsNone(engine.last_emotion)
        self.assertIsNone(engine.four_channel_fatigue.ema)
        self.assertIsNone(engine.four_channel_fatigue.stream.features())
        self.assertFalse(engine.covariance_stream.ready)
        return engine, session

    def test_worker_saves_its_own_partial_and_complete_state_across_abrupt_exit(self):
        parent, session = processor(), self.session()
        raw = generated_signal(32000, 88)
        clean = CausalEEGFilter().process(raw)
        worker = self.worker_class(parent, calibration_session=session)
        try:
            self.feed(worker, raw[:6000], clean[:6000], parent.scale)
            self.assertEqual(worker.calibration_progress, 3)
            self.assertEqual(parent.calibration_progress, 0)  # Parent fork copy is stale.
            self.assertEqual(len(json.loads(self.path.read_text())['fatigue']['baseline']), 3)
            worker.process.kill()
            worker.process.join(timeout=2)
            self.assertEqual(worker.process.exitcode, -9)
        finally:
            worker.close()
        restored, session = self.restored()
        self.assertEqual(restored.calibration_progress, 3)
        self.assertFalse(restored.calibration_ready)
        worker = self.worker_class(restored, calibration_session=session)
        try:
            self.feed(worker, raw[6000:], clean[6000:], restored.scale)
            self.assertEqual(worker.calibration_progress, 15)
            self.assertTrue(worker.calibration_ready)
            self.assertEqual(worker.checkpoint_write_failures, 0)
        finally:
            worker.close()
        restored, _ = self.restored()
        self.assertEqual(restored.calibration_progress, 15)
        self.assertTrue(restored.sqi_monitor.calibrated_channels.all())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_stream_invalidation_keeps_completed_checkpoint_and_baseline(self):
        engine, session = self.seed(15)
        before = self.path.read_bytes()
        worker = self.worker_class(engine, calibration_session=session)
        try:
            worker.invalidate()
            self.assertEqual(worker.calibration_progress, 15)
            self.assertTrue(worker.calibration_ready)
            self.assertEqual(self.path.read_bytes(), before)
            raw = generated_signal(2000, 90)
            self.feed(worker, raw, CausalEEGFilter().process(raw), engine.scale)
            self.assertEqual(worker.calibration_progress, 15)
            self.assertEqual(self.path.read_bytes(), before)
        finally:
            worker.close()

    def test_new_wearing_does_not_allow_inflight_old_window_to_recreate_checkpoint(self):
        engine, session = self.seed(15)
        context = multiprocessing.get_context('fork')
        started, release, finished = context.Event(), context.Event(), context.Event()
        append = engine.append
        count = [0]
        def gated(*args):
            if count[0] == 0:
                started.set()
                if not release.wait(5):
                    raise TimeoutError('Test release absent')
            count[0] += 1
            result = append(*args)
            if count[0] == 2000:
                finished.set()
            return result
        engine.append = gated
        worker = self.worker_class(engine, calibration_session=session)
        raw = generated_signal(2000, 90)
        clean = CausalEEGFilter().process(raw)
        try:
            self.assertTrue(worker.submit(raw / engine.scale, clean, np.zeros(2000, dtype=bool),
                counters(2000), time.monotonic()))
            self.assertTrue(started.wait(2))
            worker.invalidate(new_wearing=True, wear_id='b' * 32)
            self.assertFalse(self.path.exists())
            self.assertEqual(worker.calibration_progress, 0)
            release.set()
            self.assertTrue(finished.wait(8))
            self.feed(worker, raw, clean, engine.scale)
            saved = json.loads(self.path.read_text())
            self.assertEqual(saved['context']['wear_id'], 'b' * 32)
            self.assertEqual(len(saved['fatigue']['baseline']), 1)
            self.assertFalse(any(saved['sqi']['calibrated_channels']))
            self.assertFalse(worker.calibration_ready)
        finally:
            release.set()
            worker.close()

    def test_checkpoint_write_error_is_counted_not_reported_as_saved(self):
        engine, session = processor(), self.session()
        with patch.object(session, 'save', side_effect=OSError('injected storage failure')):
            worker = self.worker_class(engine, calibration_session=session)
        try:
            raw = generated_signal(2000, 90)
            self.feed(worker, raw, CausalEEGFilter().process(raw), engine.scale)
            self.assertEqual(worker.checkpoint_write_failures, 1)
            self.assertFalse(self.path.exists())
            self.assertEqual(worker.calibration_progress, 1)
        finally:
            worker.close()

    def test_invalid_new_wear_identity_cannot_delete_the_checkpoint(self):
        engine, session = self.seed(1)
        worker = self.worker_class(engine, calibration_session=session)
        before = self.path.read_bytes()
        try:
            for value in (None, '', 'G' * 32, 'b' * 31, 'b' * 33):
                with self.assertRaises(ValueError):
                    worker.invalidate(new_wearing=True, wear_id=value)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(worker.generation[:], [0, 0])
        finally:
            worker.close()

    def test_checkpoint_cli_never_opens_hardware_or_formal_outputs(self):
        import sys
        import cyton_guardianloop as live
        cases = ([], ['--isolated-primary-worker'],
            ['--isolated-primary-worker', '--status-file', '/run/guardianloop/status.json'],
            ['--isolated-primary-worker', '--status-file', '/dev/shm/gl-primary-recovery-test/status.json',
             '--telemetry-file', '/run/guardianloop/telemetry.json'])
        for flags in cases:
            with self.subTest(flags=flags), contextlib.redirect_stderr(io.StringIO()), \
                    patch.object(sys, 'argv', ['private', '--port', '/dev/null', '--esp32-url', '',
                        '--isolated-primary-checkpoint', *flags]), \
                    patch.object(live.os, 'open') as opened:
                with self.assertRaises(SystemExit):
                    live.main()
                opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()

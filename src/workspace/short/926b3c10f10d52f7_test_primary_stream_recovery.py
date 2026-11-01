"""Recovery parity and fault-burst checks; no USB, PL, or physical control."""

import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from cyton_covariance import CovarianceFeatureStream
from cyton_fatigue import FourChannelFatigue
from cyton_sqi import CausalEEGFilter
from seed_quality_runtime import SeedQualityRuntime
from seed_replay_check import CausalResampler, FeatureStream


HERE = Path(__file__).resolve().parent
CAP = ('F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2')
FATIGUE_MODEL = Path(os.environ.get('GL_TEST_FATIGUE_MODEL', str(
    HERE.parent / 'viformer_z15' / 'output' / 'cyton_montage_fatigue_v2' /
    'cyton_fatigue_overlap4.json')))


class PrimaryRecoveryTests(unittest.TestCase):
    def test_seed_signal_reset_matches_fresh_filters_and_features(self):
        values = np.random.default_rng(84).normal(size=(4000, 8))
        resampler = CausalResampler()
        coefficients = resampler.h
        resampler.process(values)
        resampler.reset()
        self.assertIs(resampler.h, coefficients)
        np.testing.assert_array_equal(resampler.process(values), CausalResampler().process(values))
        features = FeatureStream()
        coefficients = features.sos
        features.process(values)
        features.reset()
        self.assertIs(features.sos, coefficients)
        self.assertEqual(features.warmup, 400)
        self.assertEqual(features.pending.shape, (5, 0, 8))
        np.testing.assert_array_equal(features.process(values), FeatureStream().process(values))
        weights = dict(weight=np.ones((3, 180)), bias=np.zeros(3), classes=np.array([-1, 0, 1]))
        runtime = SeedQualityRuntime(weights)
        objects = (runtime.prefilter, runtime.resampler, runtime.features)
        runtime._accept_feature(np.ones(180))
        runtime.disconnect('test_fault')
        self.assertEqual(objects, (runtime.prefilter, runtime.resampler, runtime.features))
        self.assertEqual(runtime.accepted_windows, 0)
        self.assertIsNone(runtime.last_prediction)
        self.assertTrue(runtime.warming)
        self.assertEqual(runtime.epoch, 1)

    def test_filter_reset_matches_fresh_instance(self):
        values = np.random.default_rng(81).normal(size=(400, 8))
        engine = CausalEEGFilter()
        coefficients = engine.sos
        engine.process(values + 500)
        engine.reset()
        self.assertIs(engine.sos, coefficients)
        self.assertIsNone(engine.origin)
        np.testing.assert_array_equal(engine.process(values), CausalEEGFilter().process(values))

    def test_covariance_reset_discards_old_window(self):
        values = np.random.default_rng(82).normal(size=(3300, 8))
        for storage in ('deque', 'array'):
            with self.subTest(storage=storage):
                engine = CovarianceFeatureStream(CAP, storage=storage)
                coefficients = engine.sos
                engine.append(values + 500)
                self.assertTrue(engine.ready)
                engine.reset()
                self.assertIs(engine.sos, coefficients)
                self.assertFalse(engine.ready)
                with self.assertRaisesRegex(ValueError, '12 seconds'):
                    engine.feature()
                fresh = CovarianceFeatureStream(CAP, storage=storage)
                for chunk in np.array_split(values, 17):
                    engine.append(chunk)
                    fresh.append(chunk)
                np.testing.assert_array_equal(engine.feature(), fresh.feature())

    def test_fatigue_reset_reuses_weights_and_requires_full_recalibration(self):
        model_path = FATIGUE_MODEL
        engine = FourChannelFatigue(model_path)
        weights = engine.model
        coefficients = engine.stream.sos
        rng = np.random.default_rng(83)
        for _ in range(16):
            engine.append(rng.normal(0, 5, size=(2000, 8)))
            result = engine.process_window(True, True)
        self.assertIn(result['state'], ('NORMAL', 'MILD', 'SEVERE'))
        with patch.object(Path, 'read_text', side_effect=AssertionError('Model reread during reset')):
            engine.reset()
        self.assertIs(engine.model, weights)
        self.assertIs(engine.stream.sos, coefficients)
        self.assertEqual(engine.baseline, [])
        self.assertEqual(engine.window, 0)
        self.assertIsNone(engine.mean)
        self.assertIsNone(engine.scale)
        self.assertIsNone(engine.ema)
        self.assertIsNone(engine.stream.features())
        fresh = FourChannelFatigue(model_path)
        values = rng.normal(0, 5, size=(2000, 8))
        for item in (engine, fresh):
            item.append(values)
        np.testing.assert_array_equal(engine.stream.features(), fresh.stream.features())
        result = engine.process_window(True, True)
        self.assertEqual(result, fresh.process_window(True, True))
        self.assertEqual(result['state'], 'CALIBRATING')
        self.assertEqual(result['calibration_current'], 1)
        self.assertNotIn('perclos', result)

    def test_stream_reset_preserves_baseline_but_requires_fresh_quality_window(self):
        engine = FourChannelFatigue(FATIGUE_MODEL)
        rng = np.random.default_rng(84)
        for _ in range(16):
            engine.append(rng.normal(0, 5, (2000, 8)))
            engine.process_window(True, True)
        mean, scale = engine.mean.copy(), engine.scale.copy()
        engine.reset_stream()
        np.testing.assert_array_equal(engine.mean, mean)
        np.testing.assert_array_equal(engine.scale, scale)
        self.assertEqual(len(engine.baseline), 15)
        self.assertIsNone(engine.ema)
        self.assertFalse(engine.process_window(True, True)['valid'])
        engine.append(rng.normal(0, 5, (2000, 8)))
        self.assertFalse(engine.process_window(False, True)['valid'])
        self.assertFalse(engine.process_window(True, False)['valid'])
        result = engine.process_window(True, True)
        self.assertIn(result['state'], ('NORMAL', 'MILD', 'SEVERE'))
        self.assertEqual(result['calibration_current'], 15)

    def test_partial_accepted_calibration_survives_stream_reset(self):
        engine = FourChannelFatigue(FATIGUE_MODEL)
        engine.append(np.random.default_rng(85).normal(0, 5, (2000, 8)))
        engine.process_window(True, True)
        engine.reset_stream()
        self.assertEqual(len(engine.baseline), 1)
        self.assertIsNone(engine.mean)
        self.assertFalse(engine.process_window(True, True)['valid'])

    @unittest.skipUnless(os.name == 'posix', 'Main loop requires termios')
    def test_main_coalesces_bad_burst_and_preserves_recording_counters(self):
        import cyton_guardianloop as live

        def frames(*args, **kwargs):
            for index in range(300):
                packet = bytes((0xA0, index % 256)) + bytes(30) + bytes((0xC0,))
                yield packet, 1 if 25 <= index < 125 else 0, 100. + index / 250

        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            for name in ('configure_serial', 'configure_eeg_channels', 'write_command'):
                stack.enter_context(patch.object(live, name))
            stack.enter_context(patch.object(live.termios, 'tcflush'))
            stack.enter_context(patch.object(live.signal, 'signal'))
            stack.enter_context(patch.object(live.time, 'sleep'))
            stack.enter_context(patch.object(live.time, 'monotonic', return_value=100.4))
            stack.enter_context(patch.object(live, 'packets', side_effect=frames))
            stack.enter_context(patch.object(live, 'SeedShadow', return_value=None))
            stack.enter_context(patch.object(live, 'SSVEPReaderRuntime', return_value=None))
            stack.enter_context(patch.object(live, 'TelemetryWriter'))
            recorder = stack.enter_context(patch.object(live, 'TrialRecorder')).return_value
            publish = stack.enter_context(patch.object(live, 'publish_result'))
            factory = stack.enter_context(patch.object(live, 'FourChannelFatigue', wraps=FourChannelFatigue))
            reset = stack.enter_context(patch.object(FourChannelFatigue, 'reset', autospec=True,
                                                      side_effect=FourChannelFatigue.reset))
            reset_stream = stack.enter_context(patch.object(FourChannelFatigue, 'reset_stream', autospec=True,
                                                      side_effect=FourChannelFatigue.reset_stream))
            stack.enter_context(patch.object(sys, 'argv', [
                'recovery-test', '--port', '/dev/null', '--esp32-url', '',
                '--fatigue-model', str(FATIGUE_MODEL),
                '--covariance-model', str(Path(directory) / 'absent-covariance'),
                '--emotion-model', str(Path(directory) / 'absent-emotion'),
                '--status-file', str(Path(directory) / 'status.json'),
                '--telemetry-file', str(Path(directory) / 'telemetry.json')]))
            live.main()
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(reset.call_count, 1)  # Calibration is not wiped by a burst.
            self.assertEqual(reset_stream.call_count, 2)
            self.assertEqual(recorder.append.call_count, 300)
            faults = [call.args[0] for call in publish.call_args_list
                      if call.args[0].get('reason') == 'MALFORMED_STREAM']
            self.assertEqual(len(faults), 1)
            self.assertFalse(faults[0]['valid'])
            self.assertFalse(faults[0]['emotion']['valid'])
            self.assertTrue(all(not call.args[0]['valid'] for call in publish.call_args_list))


if __name__ == '__main__':
    unittest.main()

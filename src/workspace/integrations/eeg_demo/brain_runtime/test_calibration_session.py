import json
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from calibration_session import CalibrationSession
from cyton_fatigue import FourChannelFatigue
from cyton_sqi import CytonSQIMonitor
from test_primary_stream_recovery import FATIGUE_MODEL


@unittest.skipUnless(os.name == 'posix', 'Private checkpoint ownership is a Linux contract')
class CalibrationSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'calibration.json'
        self.context = dict(boot='test-boot', channels=['fixed8'], model='test-model')
        self.sqi = CytonSQIMonitor()
        self.fatigue = FourChannelFatigue(FATIGUE_MODEL)
        t = np.arange(2000) / 250
        self.clean = np.stack([20*np.sin(2*np.pi*(8+i)*t) for i in range(8)], axis=1)

    def calibrate(self, count):
        for _ in range(count):
            self.sqi.process(self.clean)
            self.fatigue.append(self.clean)
            self.fatigue.process_window(True, True)

    def test_process_restart_restores_only_calibration_not_results(self):
        self.calibrate(16)
        session = CalibrationSession(self.path, self.context)
        self.assertTrue(session.save(self.sqi, self.fatigue))
        self.assertFalse(session.save(self.sqi, self.fatigue))
        new_sqi, new_fatigue = CytonSQIMonitor(), FourChannelFatigue(FATIGUE_MODEL)
        self.assertTrue(session.load(new_sqi, new_fatigue))
        self.assertEqual(len(new_fatigue.baseline), 15)
        np.testing.assert_array_equal(new_fatigue.mean, self.fatigue.mean)
        self.assertTrue(new_sqi.calibrated_channels.all())
        self.assertIsNone(new_fatigue.ema)
        self.assertIsNone(new_fatigue.stream.features())
        self.assertFalse(new_fatigue.process_window(True, True)['valid'])

    def test_partial_progress_is_retained_without_marking_complete(self):
        self.calibrate(3)
        session = CalibrationSession(self.path, self.context)
        session.save(self.sqi, self.fatigue)
        sqi, fatigue = CytonSQIMonitor(), FourChannelFatigue(FATIGUE_MODEL)
        self.assertTrue(session.load(sqi, fatigue))
        self.assertEqual(len(fatigue.baseline), 3)
        self.assertFalse(sqi.calibrated_channels.any())
        self.assertIsNone(fatigue.mean)

    def test_other_boot_model_or_montage_cannot_reuse_calibration(self):
        self.calibrate(1)
        CalibrationSession(self.path, self.context).save(self.sqi, self.fatigue)
        for key in self.context:
            other = dict(self.context, **{key:'different'})
            self.assertFalse(CalibrationSession(self.path, other).load(self.sqi, self.fatigue))

    def test_malformed_checkpoint_is_transactional_and_never_ready(self):
        self.calibrate(15)
        session = CalibrationSession(self.path, self.context)
        session.save(self.sqi, self.fatigue)
        data = json.loads(self.path.read_text())
        data['fatigue']['scale'][0] = -1
        self.path.write_text(json.dumps(data))
        sqi, fatigue = CytonSQIMonitor(), FourChannelFatigue(FATIGUE_MODEL)
        with self.assertRaises(ValueError): session.load(sqi, fatigue)
        self.assertFalse(sqi.calibrated_channels.any())
        self.assertIsNone(fatigue.mean)

    def test_world_readable_checkpoint_rejected(self):
        self.calibrate(1)
        session = CalibrationSession(self.path, self.context)
        session.save(self.sqi, self.fatigue)
        self.path.chmod(0o644)
        with self.assertRaises(ValueError): session.load(self.sqi, self.fatigue)

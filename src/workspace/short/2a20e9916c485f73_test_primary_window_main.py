"""Same full-loop results with old/new window snapshots; isolated generated input."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_calibration_main as calibration_tests
from test_primary_windows import reference, sequential_sqi


@unittest.skipUnless(os.name == 'posix', 'The main loop requires Linux')
class PrimaryWindowMainTests(unittest.TestCase):
    def test_exact_postcalibration_emotion_and_fatigue_parity(self):
        import cyton_guardianloop as live
        outputs = []
        harness = calibration_tests.CalibrationMainTests()
        model = Path(__file__).with_name('gameemo_covariance_svm.npz')
        with patch.dict(os.environ, {'GL_COVARIANCE_STORAGE': 'array'}):
            for function, descriptors in ((reference, sequential_sqi), (live.primary_windows, live.segmented_sqi)):
                with tempfile.TemporaryDirectory() as directory, patch.object(live, 'primary_windows', function):
                    with patch('cyton_sqi.segmented_sqi', descriptors), patch.object(live, 'segmented_sqi', descriptors):
                        outputs.append(harness.run_main(directory, 39000, covariance_model=model))
        self.assertEqual(outputs[0], outputs[1])
        self.assertTrue(any(row.get('emotion', {}).get('state') == 'prediction' for row in outputs[1]))
        self.assertTrue(any(row.get('state') in ('NORMAL', 'MILD', 'SEVERE') for row in outputs[1]))


if __name__ == '__main__':
    unittest.main()

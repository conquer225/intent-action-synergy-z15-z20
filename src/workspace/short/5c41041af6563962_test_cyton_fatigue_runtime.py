"""Safety-state tests for the fixed-montage four-channel fatigue candidate."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_board_runtime import FATIGUE
from cyton_fatigue import FourChannelFatigue


class FatigueRuntimeTests(unittest.TestCase):
    def test_bad_quality_and_transport_never_calibrate_or_predict(self):
        engine = FourChannelFatigue(FATIGUE)
        rng = np.random.default_rng(20260925)
        for quality_ok, transport_ok, reason in ((False, True, "REQUIRED_CHANNEL_QUALITY"),
                                                 (True, False, "TRANSPORT")):
            engine.append(rng.normal(0, 5, (2000, 8)))
            result = engine.process_window(quality_ok, transport_ok)
            self.assertFalse(result["valid"])
            self.assertEqual(result["reason"], reason)
            self.assertEqual(result["calibration_current"], 0)
            self.assertNotIn("perclos", result)

    def test_valid_estimate_only_after_fifteen_accepted_windows(self):
        engine = FourChannelFatigue(FATIGUE)
        rng = np.random.default_rng(20260926)
        for index in range(15):
            engine.append(rng.normal(0, 5, (2000, 8)))
            result = engine.process_window(True, True)
            self.assertEqual(result["state"], "CALIBRATING")
            self.assertNotIn("perclos", result)
            self.assertEqual(result["calibration_current"], index + 1)
        engine.append(rng.normal(0, 5, (2000, 8)))
        prediction = engine.process_window(True, True)
        self.assertTrue(prediction["valid"])
        self.assertIn(prediction["state"], ("NORMAL", "MILD", "SEVERE"))
        self.assertGreaterEqual(prediction["perclos"], 0)
        self.assertLessEqual(prediction["perclos"], 1)
        engine.append(rng.normal(0, 5, (2000, 8)))
        rejected = engine.process_window(False, True)
        self.assertFalse(rejected["valid"])
        self.assertNotIn("perclos", rejected)


if __name__ == "__main__":
    unittest.main()

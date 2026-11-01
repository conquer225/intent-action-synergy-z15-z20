import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from device_telemetry import hand_telemetry

class HandTelemetryTests(unittest.TestCase):
    def test_safe_open_feedback_does_not_mean_hand_is_enabled(self):
        line = 'TELEM_V3,404,403,EMG,180,180,180,180,180,180,201,201,200,198,170,0,0,0,0,0,31,0,1,1'
        parsed = hand_telemetry(line)
        self.assertEqual(parsed['feedback_sequence'], 403)
        self.assertFalse(parsed['output_acknowledged'])
        self.assertTrue(parsed['actuator_ready'])

    def test_enabled_and_acknowledged_output_uses_tail_flag(self):
        line = 'TELEM_V3,404,403,NETWORK,180,180,180,180,180,180,201,201,200,198,170,0,0,0,0,0,31,1,1,1'
        self.assertTrue(hand_telemetry(line)['output_acknowledged'])

    def test_other_or_incomplete_record_is_not_hand_telemetry(self):
        self.assertIsNone(hand_telemetry('LINK,stm_fresh:1'))
        self.assertIsNone(hand_telemetry('TELEM_V3,404,403'))

if __name__ == '__main__': unittest.main()

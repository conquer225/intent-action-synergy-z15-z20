import unittest
from probe_checks import check_stall_continuity
class ProbeAcceptanceTests(unittest.TestCase):
    def test_hdmi_repetition_alone_cannot_pass_cpu_stall_acceptance(self):
        with self.assertRaisesRegex(RuntimeError,'camera'):
            check_stall_continuity([100,10,0],[220,10,110592000],2)
        with self.assertRaisesRegex(RuntimeError,'pixel'):
            check_stall_continuity([100,10,0],[220,70,0],2)
        row=check_stall_continuity([100,10,0],[220,70,110592000],2)
        self.assertEqual(row['camera_fps'],30);self.assertEqual(row['hdmi_hz'],60)

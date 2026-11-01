import unittest
from run_stream_sim import simulation_passed
class SimulationEvidenceTests(unittest.TestCase):
    def test_pass_banner_cannot_hide_a_real_xpm_protocol_error(self):
        self.assertFalse(simulation_passed('Error: [XPM_CDC_HANDSHAKE S-4] Destination cannot complete handshake\nSTREAM_CONTROL_PASS'))
        self.assertTrue(simulation_passed('run -all\nSTREAM_CONTROL_PASS\n$finish'))

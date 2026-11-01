"""Software checks for diagnostic identity and real receipt validation; no PYNQ."""
import unittest
from unittest.mock import patch

from hdmi_integration_probe import DiagnosticBridge
from hdmi_stimulus import ScanPump
from test_hdmi_stimulus import FakeLibrary


class BridgeTests(unittest.TestCase):
    def test_only_display_receipts_make_timing_ready_and_stop_does_not_decode_eeg(self):
        lib=FakeLibrary();pump=ScanPump(lib,lambda *_:None,clock=lambda:lib.now)
        bridge=DiagnosticBridge()
        with patch('hdmi_integration_probe.time.monotonic',lambda:lib.now):
            start=bridge.hdmi_command(dict(action='start',page_id=1))
            identity=dict(id=start['id'],page_id=1)
            bridge.hdmi_command(dict(action='presented',**identity,**pump.begin()))
            for _ in range(18):
                result=bridge.hdmi_command(dict(action='heartbeat',**identity,
                                                latches=[pump.step() for _ in range(8)]))
            self.assertTrue(result['display_timing']['ready'])
            self.assertEqual(result['source'],'display_diagnostic_not_eeg')
            self.assertFalse(result['control_enabled']);self.assertNotIn('result',result)
            bridge.hdmi_command(dict(action='stop',**identity))
            with self.assertRaises(ValueError):bridge.hdmi_command(dict(action='heartbeat',**identity,latches=[]))
        self.assertEqual(len(bridge.snapshot()[0]['latches']),144)
        self.assertTrue(bridge.snapshot()[0]['stopped'])

    def test_old_page_and_wrong_pattern_are_rejected(self):
        lib=FakeLibrary();pump=ScanPump(lib,lambda *_:None,clock=lambda:lib.now)
        bridge=DiagnosticBridge()
        with patch('hdmi_integration_probe.time.monotonic',lambda:lib.now):
            reply=bridge.hdmi_command(dict(action='start',page_id=1))
            old=dict(id=reply['id'],page_id=1)
            bridge.hdmi_command(dict(action='presented',**old,**pump.begin()))
            row=pump.step();row['pattern_mask']^=1
            with self.assertRaises(ValueError):bridge.hdmi_command(dict(action='heartbeat',**old,latches=[row]))
            new=bridge.hdmi_command(dict(action='start',page_id=2))
            self.assertNotEqual(reply['id'],new['id'])
            with self.assertRaises(ValueError):bridge.hdmi_command(dict(action='stop',**old))


if __name__=='__main__':unittest.main()

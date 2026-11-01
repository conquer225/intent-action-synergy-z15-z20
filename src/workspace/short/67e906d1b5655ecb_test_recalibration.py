"""Restart ownership: a new USB session must wait for the old process to exit."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from calibration_worker import CalibrationRestart
from guide import Guide
from selection import Selection


class RestartTests(unittest.TestCase):
    def setUp(self):
        self.state=Guide()
        self.state.phase="selection"
        self.worker=Mock()
        self.worker.process.poll.return_value=None
        self.selection=Selection()
        self.selection.hover=0
        self.selection.progress=.8
        self.menu=Mock()
        self.gate=CalibrationRestart()

    def request(self,now=10):
        return self.gate.request(self.state,self.worker,self.menu,self.selection,now)

    def test_stops_media_and_clears_progress_before_replacement(self):
        calls=Mock()
        calls.attach_mock(self.menu.close,"stop_media")
        calls.attach_mock(self.worker.abort,"stop_usb")
        self.assertTrue(self.request())
        self.assertEqual([c[0] for c in calls.mock_calls],["stop_media","stop_usb"])
        self.assertEqual(self.selection.progress,0)
        self.assertEqual(self.selection.hover,-1)
        self.assertEqual(self.state.phase,"restarting")
        self.assertIsNone(self.gate.poll(self.worker,10.1))
        self.assertTrue(self.gate.pending)

    def test_exit_is_required_and_ready_is_delivered_once(self):
        self.request()
        self.assertIsNone(self.gate.poll(self.worker,21.9))
        self.worker.process.poll.return_value=0
        self.assertEqual(self.gate.poll(self.worker,22),"ready")
        self.assertIsNone(self.gate.poll(self.worker,23))
        self.assertFalse(self.gate.pending)

    def test_old_error_exit_still_releases_ownership(self):
        self.request()
        self.worker.process.poll.return_value=1
        self.assertEqual(self.gate.poll(self.worker,11),"ready")

    def test_repeated_press_cannot_extend_wait_or_abort_twice(self):
        self.request()
        self.assertFalse(self.request(20))
        self.assertEqual(self.gate.requested_at,10)
        self.worker.abort.assert_called_once()
        self.menu.close.assert_called_once()

    def test_timeout_never_grants_ready_even_if_exit_occurs_later(self):
        self.request()
        self.assertEqual(self.gate.poll(self.worker,22),"timeout")
        self.worker.process.poll.return_value=0
        self.assertIsNone(self.gate.poll(self.worker,23))

    def test_cancel_prevents_delayed_automatic_start(self):
        self.request()
        self.gate.cancel()
        self.state.cancel()
        self.worker.process.poll.return_value=0
        self.assertIsNone(self.gate.poll(self.worker,11))
        self.assertEqual(self.state.phase,"cancelled")

    def test_only_selection_can_request_and_new_guide_clears_point_ack(self):
        for phase in ("ready","connecting","collect","compute","restarting"):
            self.state.phase=phase
            self.assertFalse(self.request())
        self.state.phase="selection"
        self.state.point=2
        self.state.ack=True
        self.assertTrue(self.request())
        self.worker.process.poll.return_value=0
        self.assertEqual(self.gate.poll(self.worker,11),"ready")
        self.state.phase="ready"
        self.state.start(11)
        self.assertEqual(self.state.phase,"prepare")
        self.assertEqual(self.state.point,0)
        self.assertIsNone(self.state.ack)


if __name__=="__main__":
    unittest.main()

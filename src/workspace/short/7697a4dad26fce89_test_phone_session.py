import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
from phone_eye_session import PhoneSession
from network_receiver import ReceiverError


class FakeReceiver:
    def __init__(self, config):
        self.operations = []
        self.closed = False

    def probe(self):
        return dict(network_mode="off", busy=False)

    def command(self, operation, source_monotonic=None):
        self.operations.append(operation)
        return dict(network_mode="off" if operation == "STOP" else "virtual", result="armed")

    def close(self):
        self.closed = True


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.native = self.root / "native"
        # A private temporary test fixture, not a hardware program.
        self.native.touch()
        self.patches = [patch("phone_eye_session.NATIVE_SHA", hashlib.sha256(b"").hexdigest()),
                        patch("phone_eye_session.NetworkReceiver", FakeReceiver),
                        patch("phone_eye_session.PhoneSession._tick_loop")]
        for active in self.patches:
            active.start()
            self.addCleanup(active.stop)

    def session(self):
        value = PhoneSession({}, self.native, self.root)
        self.addCleanup(value.close)
        return value

    def test_startup_never_opens_usb_or_arms(self):
        with patch("phone_eye_session.subprocess.Popen") as spawn:
            session = self.session()
            self.assertEqual(session.mode, "off")
            self.assertIsNone(session.worker)
            self.assertEqual(session.receiver.operations, [])
            spawn.assert_not_called()

    def test_no_calibration_no_output_and_explicit_hid_confirmation(self):
        session = self.session()
        for mode in ("virtual", "hid"):
            with self.assertRaises(ValueError):
                session.arm(mode, True)
        session.trained = True
        with self.assertRaises(ValueError):
            session.arm("hid", False)
        self.assertEqual(session.receiver.operations, [])

    def test_failed_arm_clears_gate_and_does_not_retry(self):
        session = self.session()
        session.trained = True
        with patch.object(session.gate, "arm"), patch.object(session.receiver, "command", side_effect=ReceiverError("timeout")) as command:
            with self.assertRaises(ReceiverError):
                session.arm("virtual", False)
            self.assertFalse(session.gate.armed)
            self.assertEqual(session.mode, "off")
            command.assert_called_once_with("ARM_VIRTUAL")

    def test_stop_failure_keeps_output_disarmed(self):
        session = self.session()
        session.mode, session.gate.armed = "virtual", True
        with patch.object(session.receiver, "command", side_effect=ReceiverError("timeout")) as command:
            session.disarm("test loss")
            command.assert_called_once_with("STOP")
        self.assertFalse(session.gate.armed)
        self.assertEqual(session.mode, "off")

    def test_untrained_raw_gaze_cannot_forward(self):
        session = self.session()
        class Worker:
            stdout = io.BytesIO(b'{"kind":"direction_gaze","x":0.9,"valid":true}\n')
            def poll(self):
                return 0
        worker = Worker()
        session.worker = worker
        session._read_native(worker)
        session.worker = None
        self.assertEqual(session.receiver.operations, [])
        self.assertFalse(session.trained)


if __name__ == "__main__":
    unittest.main()

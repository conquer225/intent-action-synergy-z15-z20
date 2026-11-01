import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

from mi_cued_replay import load_recording, feed_recording


class Stop:
    def __init__(self, stop_after=None):
        self.calls = 0
        self.stop_after = stop_after

    def is_set(self):
        return False

    def wait(self, duration):
        self.calls += 1
        return self.stop_after is not None and self.calls >= self.stop_after


class Sink:
    def __init__(self):
        self.received = 0
        self.reasons = []
        self.timestamps = []

    def feed(self, values, seq, **kwargs):
        self.received += len(values)
        self.timestamps.append(kwargs['received_monotonic'])
        assert len(values)==len(seq)

    def disconnect(self, reason):
        self.reasons.append(reason)


class ReplayTests(unittest.TestCase):
    def test_early_wait_does_not_create_future_timestamp(self):
        session = Sink()
        with patch('mi_cued_replay.time.monotonic',side_effect=[100,100,100.199]):
            feed_recording(session,np.ones((50,8)),np.arange(50),Stop())
        self.assertEqual(session.timestamps,[100.199])

    def test_late_wait_keeps_original_deadline_for_stale_gate(self):
        session = Sink()
        with patch('mi_cued_replay.time.monotonic',side_effect=[100,100,101]):
            feed_recording(session,np.ones((50,8)),np.arange(50),Stop())
        self.assertEqual(session.timestamps,[100.2])

    def test_exact_input_and_eof_clears_state(self):
        session = Sink()
        feed_recording(session,np.ones((525,8)),np.arange(525)%256,Stop())
        self.assertEqual(session.received,525)
        self.assertEqual(session.reasons,['replay_eof'])

    def test_user_stop_also_disconnects(self):
        session = Sink()
        feed_recording(session,np.ones((525,8)),np.arange(525)%256,Stop(2))
        self.assertEqual(session.received,50)
        self.assertEqual(session.reasons,['replay_eof'])

    def test_loader_preserves_waveform_and_wraps_counter(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'recorded.npz'
            raw = np.arange(4000).reshape(500,8)
            np.savez(path,recorded=raw,recorded_seq=np.arange(500))
            values,seq = load_recording(path)
            np.testing.assert_array_equal(values,raw)
            np.testing.assert_array_equal(seq,np.arange(500)%256)
            np.savez(path,recorded=raw,recorded_seq=(np.arange(500)%256).astype(np.uint8))
            _,seq = load_recording(path)
            np.testing.assert_array_equal(seq,np.arange(500)%256)

    def test_loader_refuses_noninteger_counter(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bad.npz'
            np.savez(path,recorded=np.ones((500,8)),recorded_seq=np.arange(500,dtype=float))
            with self.assertRaises(ValueError):
                load_recording(path)


if __name__ == '__main__':
    unittest.main()

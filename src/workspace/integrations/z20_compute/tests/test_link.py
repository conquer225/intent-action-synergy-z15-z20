import socket
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.protocol import Message
from z20_compute.link import ResultCache, SocketPeer
from z20_compute.protocol import Decoder


def prediction(sequence=1, session="peer-a"):
    return Message("result", session, sequence, 100, dict(task="face", model_version="model-a",
                   valid=True, class_id=1, scores=[0., 3., -1.], state="prediction"))


class LinkTests(unittest.TestCase):
    def test_disconnect_expiry_and_reordered_results_do_not_leave_a_label(self):
        cache = ResultCache(now=lambda: 0)
        cache.connect("peer-a")
        self.assertTrue(cache.accept(prediction(2), received_at=0))
        self.assertFalse(cache.accept(prediction(1), received_at=.1))
        self.assertEqual(cache.get("face", now=1).body["class_id"], 1)
        self.assertIsNone(cache.get("face", now=3))
        cache.disconnect()
        self.assertIsNone(cache.get("face", now=0))
        cache.connect("peer-b")
        self.assertFalse(cache.accept(prediction(99), received_at=0))

    def test_socket_peer_sends_only_bounded_latest_backlog_and_reports_eof(self):
        a, b = socket.socketpair()
        closed = threading.Event()
        peer = SocketPeer(a, lambda message: None, lambda reason: closed.set(),
                          session="peer-a", max_pending=2)
        try:
            for sequence in range(10):
                peer.offer(prediction(sequence))
            self.assertEqual(peer.dropped, 8)
            peer.start()
            b.settimeout(1)
            decoder, messages = Decoder(), []
            while len(messages) < 2:
                messages.extend(decoder.feed(b.recv(4096)))
            self.assertEqual([m.sequence for m in messages[:2]], [8, 9])
            b.close()
            self.assertTrue(closed.wait(1))
        finally:
            b.close()
            peer.close()


if __name__ == "__main__":
    unittest.main()

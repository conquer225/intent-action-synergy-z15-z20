import socket
import time
import unittest
import numpy as np
from test_runtime import EEGAdapter, Classifier
from z20_compute.runtime import RuntimeCoordinator
from z20_compute.service import BoardSession, EEGPublisher


class ServiceTests(unittest.TestCase):
    def test_loopback_eeg_results_commands_and_disconnect(self):
        left, right = socket.socketpair()
        eeg = EEGAdapter()
        runtime = RuntimeCoordinator(models={"emotion": Classifier()}, eeg_adapter=eeg)
        board = BoardSession(left, runtime)
        publisher = EEGPublisher(right)
        try:
            board.start(); publisher.start()
            publisher.offer_samples(np.ones((25, 8)), captured_ns=1000)
            publisher.set_mode("face")
            deadline = time.monotonic()+2
            while time.monotonic() < deadline:
                board.pump()
                if publisher.results.get("emotion") is not None and runtime.mode == "face": break
                time.sleep(.001)
            self.assertEqual(eeg.samples, 25)
            self.assertEqual(runtime.mode, "face")
            self.assertEqual(publisher.results.get("emotion").body["class_id"], 1)
            publisher.close()
            deadline = time.monotonic()+1
            # I/O shutdown and the asynchronous disconnect callback are distinct;
            # wait on the public invalidation outcome, not an internal I/O flag.
            while runtime.status()["emotion"]["valid"] and time.monotonic() < deadline: time.sleep(.001)
            self.assertFalse(runtime.status()["emotion"]["valid"])
        finally:
            board.close(); publisher.close(); runtime.close()


if __name__ == "__main__": unittest.main()

import sys
import threading
import time
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.video import AnalysisWorker, RingState, SnapshotReader


class VideoTests(unittest.TestCase):
    def test_slow_analysis_drops_old_frames_and_never_owns_capture(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def analyze(frame):
            calls.append(frame)
            if frame == 1:
                entered.set()
                release.wait(2)
            return frame * 10
        worker = AnalysisWorker(analyze)
        try:
            worker.submit(1, 1)
            self.assertTrue(entered.wait(1))
            start = time.monotonic()
            for frame in range(2, 101):
                worker.submit(frame, frame)
            self.assertLess(time.monotonic() - start, .2)
            self.assertEqual(calls, [1])
            release.set()
            self.assertTrue(worker.wait_for_sequence(100, 2))
            self.assertEqual(calls, [1, 100])
            self.assertEqual(worker.result().value, 1000)
            self.assertGreaterEqual(worker.dropped, 98)
        finally:
            release.set()
            self.assertTrue(worker.close())

    def test_snapshot_discards_a_buffer_overwritten_during_copy(self):
        states = iter([RingState(0, 1, 10, 100), RingState(0, 1, 13, 103)])
        source = np.full((4, 4), 7, dtype=np.uint8)
        reader = SnapshotReader(lambda: next(states), lambda index: source)
        self.assertIsNone(reader.latest())
        stable = RingState(0, 1, 14, 104)
        reader = SnapshotReader(lambda: stable, lambda index: source)
        snapshot = reader.latest()
        source[:] = 99
        self.assertEqual(int(snapshot.pixels[0, 0]), 7)
        self.assertFalse(snapshot.pixels.flags.writeable)
        self.assertIsNone(reader.latest())

    def test_mode_change_discards_inflight_results(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def analyze(frame):
            entered.set()
            release.wait(2)
            finished.set()
            return "old-face"
        worker = AnalysisWorker(analyze)
        try:
            worker.submit(1, "face")
            self.assertTrue(entered.wait(1))
            worker.invalidate()
            release.set()
            self.assertTrue(finished.wait(1))
            self.assertIsNone(worker.result())
        finally:
            release.set()
            worker.close()

    def test_result_age_is_measured_from_input_not_completion(self):
        clock = [0.0]
        worker = AnalysisWorker(lambda x: clock.__setitem__(0, 4.0) or x, now=lambda: clock[0], ttl=2)
        try:
            worker.submit(1, "stale")
            self.assertFalse(worker.wait_for_sequence(1, .05))
            self.assertIsNone(worker.result())
        finally:
            worker.close()


if __name__ == "__main__":
    unittest.main()

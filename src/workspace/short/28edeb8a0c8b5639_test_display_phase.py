"""Software-only pacing/fault simulation; never imports PYNQ or uses real MMIO."""
import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest

import numpy as np


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    process_time = monotonic

    def sleep(self, seconds):
        self.now += seconds


class Display:
    def __init__(self, clock):
        self.clock, self.index = clock, 0
        self.stalled = self.bad_latch = False

    def display_index(self):
        return self.index

    def display_frames(self):
        return 0 if self.stalled else int(self.clock.now * 60)

    def display_park(self, index):
        self.clock.now += .002
        if not self.bad_latch:
            self.index = index
        return 1

    def display_status(self):
        return 0


class Decoder:
    def __init__(self, clock):
        self.clock, self.delay, self.result, self.closed = clock, .005, 1, 0

    def video_open(self, *_):
        return 1

    def video_read_to(self, *_):
        self.clock.now += self.delay
        return self.result

    def video_close(self, *_):
        self.closed += 1


class Buffer(np.ndarray):
    def flush(self):
        pass


class DisplayPhaseTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).with_name("display_trial.py")).read_text())
        phase = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "phase")
        self.clock = Clock()
        namespace = {"np": np, "time": self.clock, "json": json}
        exec(compile(ast.Module(body=[phase], type_ignores=[]), "display_phase", "exec"), namespace)
        self.phase = namespace["phase"]
        self.display, self.decoder = Display(self.clock), Decoder(self.clock)
        self.buffers = [np.zeros((720, 1280, 3), dtype=np.uint8).view(Buffer) for _ in range(3)]
        self.cached = np.zeros((2, 720, 1280, 3), dtype=np.uint8)

    def run_phase(self, mode):
        with redirect_stdout(io.StringIO()):
            return self.phase(self.display, self.decoder, self.buffers, self.cached, Path("fake.mp4"), mode, 2)

    def test_paced_new_frames_meet_target(self):
        result = self.run_phase("copy")
        self.assertTrue(result["meets_16fps"])
        self.assertGreaterEqual(result["minimum_full_second_frames"], 16)
        self.assertEqual(self.decoder.closed, 1)

    def test_60hz_refresh_does_not_hide_slow_video(self):
        self.decoder.delay = .1
        result = self.run_phase("direct")
        self.assertFalse(result["meets_16fps"])
        self.assertGreater(result["scan_counter_delta"], result["presented_new_frames"])

    def test_cache_is_paced_instead_of_counting_refreshes(self):
        result = self.run_phase("cache")
        self.assertTrue(result["meets_16fps"])
        self.assertLessEqual(result["latched_video_fps"], 21)

    def test_stalled_scan_rejected(self):
        self.display.stalled = True
        with self.assertRaisesRegex(RuntimeError, "scan counter stalled"):
            self.run_phase("copy")
        self.assertEqual(self.decoder.closed, 1)

    def test_unlatched_buffer_rejected(self):
        self.display.bad_latch = True
        with self.assertRaisesRegex(RuntimeError, "did not latch"):
            self.run_phase("copy")

    def test_decoder_error_closes_reader(self):
        self.decoder.result = -1
        with self.assertRaisesRegex(RuntimeError, "decode failed"):
            self.run_phase("copy")
        self.assertEqual(self.decoder.closed, 1)


if __name__ == "__main__":
    unittest.main()

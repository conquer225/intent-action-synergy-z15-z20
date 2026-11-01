"""Host-only contract tests: no board device is opened."""

import sys
import hashlib
from pathlib import Path
import unittest

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pynq_guardianloop"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pl_filter_candidate"))
from pl_causal_filter import (
    KernelOwnedCausalFilter, _FRAME, _STATUS, _IOCTL_RUN, _IOCTL_STATUS,
    _IOCTL_RESET_FILTER,
)
from cyton_sqi import CausalEEGFilter
from fixed_sos import FixedSOS, quantize


class FakeOwner:
    def __init__(self):
        self.fd = 11
        self.closed = False
        self.frames = 0
        self.resets = 0
        self.fail_frame = None
        self.state = 0
        self.ever_started = 0
        self.corrupt_reply = False

    def open(self, path, flags):
        assert path == "/dev/guardianloop_dma_keeper"
        return self.fd

    def close(self, fd):
        assert fd == self.fd
        self.closed = True

    def ioctl(self, fd, request, arg, mutate=True):
        assert fd == self.fd
        if request == _IOCTL_STATUS:
            arg[:] = _STATUS.pack(1, self.state, self.ever_started, 0, 0, 0)
            return 0
        if request == _IOCTL_RESET_FILTER:
            self.resets += 1
            return 0
        assert request == _IOCTL_RUN
        self.frames += 1
        if self.frames == self.fail_frame:
            raise OSError("synthetic DMA fault")
        fields = _FRAME.unpack(arg)
        assert fields[:2] == (1, 100)
        # Echo the Q16 input as output to verify word order and state contract.
        arg[:] = _FRAME.pack(2 if self.corrupt_reply else 1, 100,
                            *fields[2:82], *fields[2:82])
        return 0


class ModelOwner(FakeOwner):
    def __init__(self):
        super().__init__()
        self.model = FixedSOS(CausalEEGFilter().sos)

    def ioctl(self, fd, request, arg, mutate=True):
        if request == _IOCTL_RESET_FILTER:
            self.model.reset()
            return super().ioctl(fd, request, arg, mutate)
        if request != _IOCTL_RUN:
            return super().ioctl(fd, request, arg, mutate)
        words = _FRAME.unpack(arg)
        output = self.model.process_quantized(
            np.asarray(words[2:82], dtype=np.int64).reshape(10, 8))
        arg[:] = _FRAME.pack(1, 100, *words[2:82], *output.reshape(-1))
        self.frames += 1
        return 0


class KernelOwnedFilterTests(unittest.TestCase):
    def build(self, fake):
        return KernelOwnedCausalFilter(open_fd=fake.open, close_fd=fake.close,
                                       ioctl=fake.ioctl)

    def test_frames_origin_and_reset(self):
        fake = FakeOwner()
        filt = self.build(fake)
        raw = np.arange(160, dtype=np.float64).reshape(20, 8) / 8
        np.testing.assert_allclose(filt.process(raw), raw - raw[0], atol=1 / 65536)
        self.assertEqual(fake.frames, 2)
        np.testing.assert_allclose(filt.process(raw[:10] + 1), raw[:10] + 1 - raw[0], atol=1 / 65536)
        filt.reset()
        self.assertEqual(fake.resets, 1)
        np.testing.assert_allclose(filt.process(raw[:10] + 1), raw[:10] - raw[0], atol=1 / 65536)
        filt.close()
        self.assertTrue(fake.closed)

    def test_uncertain_dma_never_retries_or_falls_back(self):
        fake = FakeOwner()
        fake.fail_frame = 2
        filt = self.build(fake)
        raw = np.zeros((20, 8))
        with self.assertRaises(OSError):
            filt.process(raw)
        self.assertTrue(filt.uncertain)
        with self.assertRaises(RuntimeError):
            filt.process(raw[:10])
        with self.assertRaises(RuntimeError):
            filt.reset()
        self.assertEqual(fake.frames, 2)
        filt.close()

    def test_guard_rejects_wrong_status_shape_and_range(self):
        fake = FakeOwner()
        fake.state = 2
        with self.assertRaises(RuntimeError):
            self.build(fake)
        self.assertTrue(fake.closed)
        fake = FakeOwner()
        fake.ever_started = 1
        with self.assertRaises(RuntimeError):
            self.build(fake)
        self.assertTrue(fake.closed)
        fake = FakeOwner()
        filt = self.build(fake)
        for raw, error in ((np.zeros((5, 8)), ValueError),
                           (np.full((10, 8), np.nan), ValueError),
                           (np.vstack((np.zeros((1, 8)), np.full((9, 8), 1e8))), OverflowError)):
            with self.assertRaises(error):
                filt.process(raw)
        self.assertEqual(fake.frames, 0)
        filt.close()

    def test_response_mismatch_latches_uncertain(self):
        fake = FakeOwner()
        fake.corrupt_reply = True
        filt = self.build(fake)
        with self.assertRaises(RuntimeError):
            filt.process(np.zeros((10, 8)))
        self.assertTrue(filt.uncertain)
        with self.assertRaises(RuntimeError):
            filt.reset()
        filt.close()

    def test_packet_frames_match_fixed_point_golden(self):
        fake = ModelOwner()
        filt = self.build(fake)
        rng = np.random.default_rng(20260929)
        raw = rng.normal(0, 25, (50, 8))
        for start in range(0, len(raw), 10):
            observed = filt.process(raw[start:start + 10])
            if start == 0:
                golden = FixedSOS(CausalEEGFilter().sos)
                origin = raw[0]
            expected = golden.process_quantized(quantize(raw[start:start + 10] - origin, 16, 40))
            np.testing.assert_array_equal(np.rint(observed * 65536).astype(np.int64), expected)
        self.assertEqual(fake.frames, 5)
        filt.reset()
        observed = filt.process(raw[:10])
        golden.reset()
        expected = golden.process_quantized(quantize(raw[:10] - raw[0], 16, 40))
        np.testing.assert_array_equal(np.rint(observed * 65536).astype(np.int64), expected)
        filt.close()

    def test_existing_record_matches_previously_verified_physical_output(self):
        replay_dir = (Path(__file__).resolve().parents[1] / "output" /
                      "pl_recorded_shadow_20260929")
        raw = np.load(replay_dir / "recorded_cyton" / "raw_uv.npy")
        physical = (replay_dir / "pl_output.bin").read_bytes()
        self.assertEqual(hashlib.sha256(physical).hexdigest(),
                         "973ac40b511a72036ac31be224d06205d0476a0886f00b38783d5661449e3ba6")
        fake = ModelOwner()
        filt = self.build(fake)
        try:
            result = np.concatenate([filt.process(raw[start:start + 10])
                                     for start in range(0, len(raw), 10)])
            self.assertEqual(fake.frames, 2023)
            self.assertEqual(np.rint(result * 65536).astype("<i8").tobytes(), physical)
        finally:
            filt.close()


if __name__ == "__main__":
    unittest.main()

"""Exercise the optional PL filter's session and failure semantics without hardware."""

import unittest

import numpy as np

from pl_causal_filter import (
    KernelOwnedCausalFilter, _FRAME, _IOCTL_RESET_FILTER, _IOCTL_RUN,
    _IOCTL_STATUS, _STATUS,
)


class FakeOwner:
    def __init__(self, *, state=0, fail_run=False):
        self.state = state
        self.fail_run = fail_run
        self.closed = False
        self.resets = 0

    def open(self, _path, _flags):
        return 17

    def close(self, fd):
        assert fd == 17
        self.closed = True

    def ioctl(self, fd, command, arg, *_rest):
        assert fd == 17
        if command == _IOCTL_STATUS:
            arg[:] = _STATUS.pack(1, self.state, 0, 0, 0x1000, 0x2000)
        elif command == _IOCTL_RUN:
            if self.fail_run:
                raise OSError("injected DMA error")
            request = _FRAME.unpack(arg)
            arg[:] = _FRAME.pack(*request[:82], *request[2:82])
        elif command == _IOCTL_RESET_FILTER:
            self.resets += 1
        else:
            raise AssertionError(f"unexpected ioctl {command}")


class PLFilterTest(unittest.TestCase):
    def make_filter(self, owner):
        return KernelOwnedCausalFilter(open_fd=owner.open, close_fd=owner.close,
                                       ioctl=owner.ioctl)

    def test_continuous_origin_and_reset(self):
        owner = FakeOwner()
        filt = self.make_filter(owner)
        first = np.arange(80, dtype=np.float64).reshape(10, 8) / 4
        second = first + 5
        np.testing.assert_allclose(filt.process(first), first - first[0], atol=1 / 65536)
        np.testing.assert_allclose(filt.process(second), second - first[0], atol=1 / 65536)
        filt.reset()
        self.assertEqual(owner.resets, 1)
        np.testing.assert_allclose(filt.process(second), second - second[0], atol=1 / 65536)
        filt.close()
        self.assertTrue(owner.closed)

    def test_nonfresh_owner_rejected_and_closed(self):
        owner = FakeOwner(state=2)
        with self.assertRaisesRegex(RuntimeError, "not READY"):
            self.make_filter(owner)
        self.assertTrue(owner.closed)

    def test_uncertain_run_never_retries(self):
        owner = FakeOwner(fail_run=True)
        filt = self.make_filter(owner)
        values = np.ones((10, 8), dtype=np.float64)
        with self.assertRaises(OSError):
            filt.process(values)
        owner.fail_run = False
        with self.assertRaisesRegex(RuntimeError, "ownership unknown"):
            filt.process(values)
        filt.close()

    def test_reused_payload_preserves_multiple_frames_and_echo_guard(self):
        owner = FakeOwner()
        filt = self.make_filter(owner)
        values = np.arange(160, dtype=np.float64).reshape(20, 8) / 17
        np.testing.assert_allclose(filt.process(values), values - values[0], atol=1 / 65536)
        assert filt._request is not None
        original_ioctl = owner.ioctl

        def corrupt_echo(fd, command, arg, *rest):
            original_ioctl(fd, command, arg, *rest)
            if command == _IOCTL_RUN:
                arg[8] ^= 1

        filt._ioctl = corrupt_echo
        with self.assertRaisesRegex(RuntimeError, 'input echo changed'):
            filt.process(values[:10])
        self.assertTrue(filt.uncertain)
        filt.close()


if __name__ == "__main__":
    unittest.main()

"""Optional kernel-owned PL prefilter; the production service defaults to ARM."""

import os
import struct

import numpy as np


_FRAME = struct.Struct("<II80q80q")
_STATUS = struct.Struct("<IIIIQQ")
_IOCTL_RUN = (3 << 30) | (_FRAME.size << 16) | (ord("G") << 8) | 1
_IOCTL_STATUS = (2 << 30) | (_STATUS.size << 16) | (ord("G") << 8) | 2
_IOCTL_RESET_FILTER = (ord("G") << 8) | 3
_SCALE = 65536.0
_LIMIT = 1 << 39


class KernelOwnedCausalFilter:
    """One process-owned DMA session; an uncertain transfer is never retried."""

    def __init__(self, device="/dev/guardianloop_dma_keeper", *, open_fd=os.open,
                 close_fd=os.close, ioctl=None):
        if ioctl is None:
            import fcntl
            ioctl = fcntl.ioctl
        self._ioctl = ioctl
        self._close_fd = close_fd
        self.fd = open_fd(device, os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
        self.origin = None
        self.started = False
        self.uncertain = False
        try:
            status = bytearray(_STATUS.size)
            self._ioctl(self.fd, _IOCTL_STATUS, status, True)
            version, state, ever_started, _, _, _ = _STATUS.unpack(status)
            if (version, state, ever_started) != (1, 0, 0):
                raise RuntimeError("PL DMA owner is not READY for a new session")
        except BaseException:
            self.close()
            raise

    def process(self, samples_uv):
        values = np.asarray(samples_uv, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != 8 or len(values) % 10 or not np.isfinite(values).all():
            raise ValueError("PL filter requires finite 10-sample-aligned eight-channel batches")
        if self.fd is None or self.uncertain:
            raise RuntimeError("PL DMA ownership unknown; full board recovery required")
        if not len(values):
            return values.copy()
        origin = values[0].copy() if self.origin is None else self.origin
        scaled = (values - origin) * _SCALE
        packed = np.copysign(np.floor(np.abs(scaled) + 0.5), scaled)
        if np.any(packed < -_LIMIT) or np.any(packed > _LIMIT - 1):
            raise OverflowError("EEG exceeds the signed-40 Q16 filter input")
        words = packed.astype(np.int64).reshape(-1, 80)
        output = np.empty_like(words)
        for index, frame in enumerate(words):
            request = bytearray(_FRAME.pack(1, 100, *frame, *([0] * 80)))
            try:
                self._ioctl(self.fd, _IOCTL_RUN, request, True)
            except BaseException:
                self.uncertain = True
                raise
            response = _FRAME.unpack(request)
            if response[:2] != (1, 100) or response[2:82] != tuple(int(x) for x in frame):
                self.uncertain = True
                raise RuntimeError("PL DMA response metadata or input echo changed")
            output[index] = np.asarray(response[82:], dtype=np.int64)
            self.started = True
        self.origin = origin
        return output.reshape(values.shape).astype(np.float64) / _SCALE

    def reset(self):
        """Reset filter state after a completed frame, not DMA or HP0."""
        if self.fd is None or self.uncertain:
            raise RuntimeError("PL DMA ownership unknown; full board recovery required")
        if self.started:
            try:
                self._ioctl(self.fd, _IOCTL_RESET_FILTER, 0)
            except BaseException:
                self.uncertain = True
                raise
        self.origin = None

    def close(self):
        if self.fd is not None:
            self._close_fd(self.fd)
            self.fd = None

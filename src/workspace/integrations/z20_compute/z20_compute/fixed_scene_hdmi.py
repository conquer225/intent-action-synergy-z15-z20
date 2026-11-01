"""Navigator CLG400 static HDMI owner, using its reserved RGB video ring.

The register plan follows the local Alientek experiment 38 720p mode and
Xilinx VTC/AXI VDMA 2023.1 register definitions. Physical display remains
subject to board validation.
"""
import ctypes
import mmap
import os
from pathlib import Path
import struct
import time

from .fixed_scene_package import FRAME_BYTES


VIDEO_BASE = 0x01000000
VIDEO_SIZE = 3 * FRAME_BYTES
VDMA_BASE = 0x43000000
VTC_BASE = 0x43C10000


def display_plan():
    hactive, vactive = 1280, 720
    htotal, vtotal = 1650, 750
    hsync_start, hsync_end = 1390, 1430
    vsync_start, vsync_end = 724, 729
    pair = lambda first, second: first | (second << 16)
    vtc = {
        0x60: pair(hactive, vactive),
        0x70: htotal,
        0x74: pair(vtotal, vtotal),
        0x78: pair(hsync_start, hsync_end),
        0x80: pair(vsync_start, vsync_end),
        0x8C: pair(vsync_start, vsync_end),
        0x6C: 0x7F,
        0x68: 0,
        0x94: vactive << 16,
        0x7C: pair(hactive, hactive),
        0x84: pair(hsync_start, hsync_start),
        0x88: pair(hactive, hactive),
        0x90: pair(hsync_start, hsync_start),
    }
    addresses = tuple(VIDEO_BASE + i * FRAME_BYTES for i in range(3))
    vdma = {0x5C + 4 * i: address for i, address in enumerate(addresses)}
    vdma.update({0x58: 3840, 0x54: 3840, 0x50: 720})
    return dict(vtc=vtc, vdma=vdma, frame_bytes=FRAME_BYTES, addresses=addresses,
                vtc_control=0x03FDEF06, vdma_control=0x3)


def _uio(name, expected_address, expected_size):
    matches = [p for p in Path('/sys/class/uio').glob('uio*')
               if (p / 'name').read_text().strip() == name]
    if len(matches) != 1:
        raise ValueError('expected one UIO device: ' + name)
    info = matches[0] / 'maps' / 'map0'
    if (int((info / 'addr').read_text(), 0) != expected_address
            or int((info / 'size').read_text(), 0) != expected_size
            or int((info / 'offset').read_text(), 0) != 0):
        raise ValueError('UIO device aperture differs from Navigator design')
    return matches[0]


def _word(mapping, offset):
    if offset < 0 or offset % 4:
        raise ValueError('MMIO word offset must be 32-bit aligned')
    return ctypes.c_uint32.from_buffer(mapping, offset)


def _read(mapping, offset):
    return _word(mapping, offset).value


def _write(mapping, offset, value):
    _word(mapping, offset).value = value


class NavigatorHDMI:
    """Takes exclusive ownership of the three reserved video frames."""
    def __init__(self):
        control = _uio('navigator-vdma-control', VDMA_BASE, 0x30000)
        observer = _uio('z20-video-observer', 0x43C20000, 0x10000)
        info = observer / 'maps' / 'map1'
        reserve = Path('/proc/device-tree/reserved-memory/video@1000000')
        if (int((info / 'addr').read_text(), 0) != VIDEO_BASE
                or int((info / 'size').read_text(), 0) != VIDEO_SIZE
                or (reserve / 'reg').read_bytes() != struct.pack('>II', VIDEO_BASE, VIDEO_SIZE)
                or not (reserve / 'no-map').is_file()):
            raise ValueError('reserved video ring does not match Navigator design')
        self.fds = []
        self.maps = []
        try:
            for device, size, offset in (('/dev/' + control.name, 0x30000, 0),
                                         ('/dev/' + observer.name, VIDEO_SIZE, mmap.PAGESIZE),
                                         ('/dev/mem', mmap.PAGESIZE, VTC_BASE)):
                fd = os.open(device, os.O_RDWR | os.O_SYNC)
                self.fds.append(fd)
                self.maps.append(mmap.mmap(fd, size, access=mmap.ACCESS_WRITE, offset=offset))
        except BaseException:
            self.close()
            raise
        self.control, self.video, self.vtc = self.maps
        if _read(self.vtc, 0x10) in (0, 0xFFFFFFFF):
            self.close()
            raise ValueError('VTC identity register is absent')

    def _stop_channel(self, base):
        _write(self.control, base, _read(self.control, base) & ~1)
        end = time.monotonic() + 1.0
        while not _read(self.control, base + 4) & 1:
            if time.monotonic() > end:
                raise TimeoutError('VDMA did not halt')
            time.sleep(.005)

    def show(self, frame):
        if len(frame) != FRAME_BYTES:
            raise ValueError('expected one 1280x720 RGB888 frame')
        plan = display_plan()
        # Camera S2MM must be halted before writing to its former ring.
        for base in (0x30, 0x10030):
            if _read(self.control, base) & 1:
                self._stop_channel(base)
        mm2s = 0x20000
        if _read(self.control, mm2s) & 1:
            self._stop_channel(mm2s)
        _write(self.vtc, 0, _read(self.vtc, 0) & ~4)
        for i in range(3):
            self.video[i * FRAME_BYTES:(i + 1) * FRAME_BYTES] = frame
        _write(self.control, mm2s, 4)
        end = time.monotonic() + 1.0
        while _read(self.control, mm2s) & 4:
            if time.monotonic() > end:
                raise TimeoutError('display VDMA reset timed out')
            time.sleep(.005)
        _write(self.control, mm2s + 4, 0xFFFFFFFF)
        for offset, value in plan['vdma'].items():
            if offset != 0x50:
                _write(self.control, mm2s + offset, value)
        for offset, value in plan['vtc'].items():
            _write(self.vtc, offset, value)
        _write(self.vtc, 0, plan['vtc_control'])
        _write(self.control, mm2s, plan['vdma_control'])
        _write(self.control, mm2s + 0x50, plan['vdma'][0x50])
        status = _read(self.control, mm2s + 4)
        if status & 0xF0:
            raise RuntimeError('display VDMA status error: 0x{:08x}'.format(status))
        return status

    def close(self):
        for mapping in reversed(getattr(self, 'maps', [])):
            mapping.close()
        for fd in reversed(getattr(self, 'fds', [])):
            os.close(fd)
        self.maps, self.fds = [], []

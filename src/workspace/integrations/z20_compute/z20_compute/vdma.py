"""Geometry for two RGB888 writers composing one continuous display surface.

Returns configuration data only. The board startup owner must configure VDMA;
analysis must never use this module to restart or park a running video channel.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelLayout:
    hsize: int                 # active bytes per line, not pixels
    stride: int                # bytes between line starts
    height: int
    addresses: tuple


@dataclass(frozen=True)
class StereoLayout:
    left: ChannelLayout
    right: ChannelLayout
    display: ChannelLayout
    required_bytes: int


def stereo_layout(base, pool_size, *, camera_width=640, height=720, stores=3):
    if (any(type(v) is not int for v in (base, pool_size, camera_width, height, stores))
            or base <= 0 or base % 64 or pool_size <= 0 or base+pool_size > 0x40000000
            or camera_width <= 0 or camera_width*3 % 64 or height <= 0
            or stores != 3):
        raise ValueError('expected aligned low-DDR pool and three RGB888 frame stores')
    active = camera_width*3
    stride = 2*active
    frame_bytes = stride*height
    if stride > 0xffff or height > 0x1fff or frame_bytes*stores > pool_size:
        raise ValueError('frame geometry exceeds VDMA fields or reserved pool')
    addresses = tuple(base+i*frame_bytes for i in range(stores))
    return StereoLayout(ChannelLayout(active, stride, height, addresses),
                        ChannelLayout(active, stride, height, tuple(a+active for a in addresses)),
                        ChannelLayout(stride, stride, height, addresses), frame_bytes*stores)

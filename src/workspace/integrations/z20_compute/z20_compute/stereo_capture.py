"""Prepare an already stable side-by-side snapshot for board-local stereo.

This module does not acquire a frame or configure video hardware. Independent
camera exposures are not synchronized by splitting a composite memory image.
"""
from dataclasses import dataclass
import cv2
import numpy as np
from .video import FrameSnapshot


@dataclass(frozen=True)
class PreparedStereo:
    frame: FrameSnapshot
    capture_mode: str


def prepare_stereo_snapshot(frame, *, pixel_order, source_size=(1280, 720), output_size=(320, 240)):
    for size in (source_size, output_size):
        if (not isinstance(size, (tuple, list)) or len(size) != 2
                or any(type(value) is not int or value <= 0 for value in size)):
            raise ValueError('image sizes must contain two positive integers')
    width, height = source_size
    if (pixel_order not in ('RGB', 'BGR') or width % 2
            or output_size[0] > width//2 or output_size[1] > height
            or not isinstance(frame.pixels, np.ndarray) or frame.pixels.dtype != np.uint8
            or frame.pixels.flags.writeable or frame.pixels.shape != (height, width, 3)):
        raise ValueError('stable uint8 side-by-side frame and explicit RGB/BGR order required')
    conversion = cv2.COLOR_RGB2GRAY if pixel_order == 'RGB' else cv2.COLOR_BGR2GRAY
    gray = [cv2.cvtColor(image, conversion) for image in
            (frame.pixels[:, :width//2], frame.pixels[:, width//2:])]
    pixels = np.stack([cv2.resize(image, output_size, interpolation=cv2.INTER_AREA) for image in gray])
    pixels.flags.writeable = False
    mode = f'z20-sbs-{width//2}x{height}-{pixel_order}-gray-{output_size[0]}x{output_size[1]}'
    return PreparedStereo(FrameSnapshot(frame.sequence, frame.captured_ns, pixels), mode)

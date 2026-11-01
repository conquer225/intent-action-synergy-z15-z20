"""Confine a safely rejected camera entry to its optional HDMI mode."""
from .continuous import CameraStartError


def service_vision(vision, display, now):
    try:
        vision.service(now)
    except CameraStartError as error:
        stream=vision.continuous
        if stream is None or stream.active or stream.buffers:
            raise
        # start() has already verified native DMA close before freeing buffers.
        # Any further cleanup failure must reach the original PL recovery path.
        vision.leave()
        display.controller._enter('home',now)
        display.buffer_pages.clear()
        display.calibration_view=None
        return str(error)
    return None

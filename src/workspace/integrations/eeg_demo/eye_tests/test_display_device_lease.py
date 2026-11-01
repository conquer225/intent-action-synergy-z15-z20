"""Device label changes must fit the existing control lease on a slow renderer."""
import sys
import time
from pathlib import Path
import unittest

import numpy as np
from PIL import ImageFont

from test_device_link import Peer
from test_eye_devices import EyeDeviceController
from guardianloop_system.device_link import DeviceLink

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from system_hdmi import UnifiedDisplay


class SlowRenderer:
    def __init__(self):
        paths = ('C:/Windows/Fonts/simsun.ttc',
                 '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf')
        font = next(Path(p) for p in paths if Path(p).is_file())
        self.fonts = {n: ImageFont.truetype(str(font), n) for n in (24, 44)}
        self.latin_fonts = self.fonts

    def text_width(self, text, size):
        return self.fonts[size].getmask(str(text)).size[0]

    def wrapped(self, text, size, width, lines):
        return [text]

    def write_text(self, draw, x, y, text, size, color):
        # Simulate rasterization cost, independently of a host computer's CPU.
        time.sleep(.045)
        draw.text((x, y), text, font=self.fonts[size], fill=color)


class DisplayDeviceLeaseTests(unittest.TestCase):
    def test_enable_labels_keep_connection_but_a_stalled_loop_still_revokes(self):
        peer = Peer()
        link = DeviceLink('127.0.0.1', peer.port)
        try:
            display = UnifiedDisplay.__new__(UnifiedDisplay)
            display.controller = EyeDeviceController(link, time.monotonic())
            display.controller._enter('pendulum_balance', time.monotonic())
            display.device_link = link
            display.renderer = SlowRenderer()
            display.shells = {'pendulum_balance': np.zeros((720, 1280, 3), np.uint8)}
            display.overlays = {}
            display.overlay_key = None
            display.frequency_state = None
            # The disabled page is prepared before the user can enable it.
            display.refresh_labels({}, {}, 'clip')
            link.service(True)
            self.assertTrue(link.request('pendulum', 'enable'))
            deadline = time.monotonic() + 2
            while link.snapshot()['enabled'] is None and time.monotonic() < deadline:
                link.service(True)
                time.sleep(.01)
            self.assertEqual(link.snapshot()['enabled'], 'pendulum')
            display.controller.device_update(time.monotonic())
            link.service(True)
            display.refresh_labels({}, {}, 'clip')
            self.assertEqual(link.snapshot()['enabled'], 'pendulum',
                             'painting the acknowledged enable must not expire the lease')
            # Caching must not weaken the independent watchdog.
            self.assertTrue(peer.closed.wait(.8))
            self.assertIsNone(link.snapshot()['enabled'])
        finally:
            link.close()
            peer.close()


if __name__ == '__main__':
    unittest.main()

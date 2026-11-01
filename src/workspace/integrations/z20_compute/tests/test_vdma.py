import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.vdma import stereo_layout


class VdmaLayoutTests(unittest.TestCase):
    def test_pool_and_alignment_errors_are_rejected_before_any_configuration(self):
        for kwargs in [dict(pool_size=8294399), dict(base=0x10000001),
                       dict(base=0x3ff00000), dict(camera_width=641),
                       dict(height=0), dict(stores=2), dict(camera_width=True),
                       dict(camera_width=16384, height=1)]:
            args = dict(base=0x10000000, pool_size=32*1024*1024)
            args.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                stereo_layout(**args)

    def test_two_half_width_writers_share_display_stride_and_frame_pitch(self):
        layout = stereo_layout(0x10000000, 32*1024*1024)
        self.assertEqual(layout.left.hsize, 1920)
        self.assertEqual(layout.right.hsize, 1920)
        self.assertEqual(layout.display.hsize, 3840)
        self.assertEqual(layout.left.stride, 3840)
        self.assertEqual(layout.right.stride, 3840)
        self.assertEqual(layout.left.addresses, (0x10000000, 0x102a3000, 0x10546000))
        self.assertEqual(layout.right.addresses, (0x10000780, 0x102a3780, 0x10546780))
        self.assertEqual(layout.display.addresses, layout.left.addresses)
        self.assertEqual(layout.required_bytes, 8294400)


if __name__ == '__main__': unittest.main()

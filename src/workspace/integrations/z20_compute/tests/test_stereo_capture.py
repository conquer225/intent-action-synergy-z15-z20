import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.video import FrameSnapshot
from z20_compute.stereo_capture import prepare_stereo_snapshot


class StereoCaptureTests(unittest.TestCase):
    def test_default_composite_reaches_async_stereo_with_known_metric_depth(self):
        from z20_compute.stereo import Calibration, StereoProcessor
        from z20_compute.runtime import RuntimeCoordinator
        left = np.random.default_rng(11).integers(0, 256, (240, 320), dtype=np.uint8)
        right = np.zeros_like(left)
        right[:, :-8] = left[:, 8:]
        composite = np.concatenate([np.repeat(np.repeat(a, 3, axis=0), 2, axis=1)
                                    for a in (left, right)], axis=1)
        composite = np.repeat(composite[:, :, None], 3, axis=2)
        composite.flags.writeable = False
        prepared = prepare_stereo_snapshot(FrameSnapshot(9, 100, composite), pixel_order='BGR')
        k = [[100, 0, 160], [0, 100, 120], [0, 0, 1]]
        calibration = Calibration((320, 240), k, [0]*5, k, [0]*5,
                                  np.eye(3), [-.1, 0, 0], prepared.capture_mode)
        runtime = RuntimeCoordinator(stereo=StereoProcessor(calibration))
        try:
            runtime.set_mode('stereo')
            self.assertTrue(runtime.submit_frame(prepared.frame, capture_mode=prepared.capture_mode))
            self.assertTrue(runtime.visual.wait_for_sequence(9, 2))
            status = runtime.status()['stereo']
            self.assertTrue(status['valid'])
            # Independent pinhole example: f=100 px, baseline=.1 m, disparity=8 px.
            self.assertAlmostEqual(status['values']['distance_m'], 1.25, delta=.05)
            self.assertEqual(status['backend'], 'PS_StereoBM')
            self.assertEqual(composite.shape, (720, 1280, 3))
            self.assertFalse(composite.flags.writeable)
        finally:
            self.assertTrue(runtime.close())

    def test_rejects_unstable_or_mismatched_capture_instead_of_guessing(self):
        pixels = np.zeros((2, 8, 3), np.uint8)
        pixels.flags.writeable = False
        defaults = dict(pixel_order='RGB', source_size=(8, 2), output_size=(4, 2))
        for array, changes in [(pixels.copy(), {}), (pixels.astype(np.float32), {}),
                               (pixels, dict(pixel_order='automatic')),
                               (pixels, dict(source_size=(7, 2))),
                               (pixels, dict(source_size=(10, 2))),
                               (pixels, dict(output_size=(0, 2))),
                               (pixels, dict(output_size=(5, 2)))]:
            args = dict(defaults, **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                prepare_stereo_snapshot(FrameSnapshot(1, 2, array), **args)

    def test_split_gray_conversion_preserves_identity_and_owns_output(self):
        pixels = np.zeros((2, 8, 3), np.uint8)
        pixels[:, :4] = [255, 0, 0]
        pixels[:, 4:] = [0, 0, 255]
        pixels.flags.writeable = False
        prepared = prepare_stereo_snapshot(FrameSnapshot(17, 12345, pixels),
                                           pixel_order='RGB', source_size=(8, 2), output_size=(4, 2))
        self.assertEqual(prepared.frame.sequence, 17)
        self.assertEqual(prepared.frame.captured_ns, 12345)
        self.assertEqual(prepared.frame.pixels.shape, (2, 2, 4))
        np.testing.assert_array_equal(prepared.frame.pixels[0], np.full((2, 4), 76, np.uint8))
        np.testing.assert_array_equal(prepared.frame.pixels[1], np.full((2, 4), 29, np.uint8))
        self.assertFalse(prepared.frame.pixels.flags.writeable)
        self.assertFalse(np.shares_memory(prepared.frame.pixels, pixels))
        self.assertEqual(prepared.capture_mode, 'z20-sbs-4x2-RGB-gray-4x2')


if __name__ == '__main__': unittest.main()

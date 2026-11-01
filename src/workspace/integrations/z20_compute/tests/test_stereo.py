import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.stereo import Calibration, StereoProcessor, write_ply


def calibration():
    return Calibration((320, 240), [[100, 0, 160], [0, 100, 120], [0, 0, 1]],
                       [0]*5, [[100, 0, 160], [0, 100, 120], [0, 0, 1]], [0]*5,
                       np.eye(3).tolist(), [-.1, 0, 0], "test-gray320")


class StereoTests(unittest.TestCase):
    def test_known_disparity_has_metre_scale_and_invalid_depth_is_excluded(self):
        processor = StereoProcessor(calibration())
        disparity = np.full((240, 320), 10., dtype=np.float32)
        disparity[:20] = 0
        result = processor.from_disparity(disparity, roi=(140, 100, 40, 40))
        self.assertAlmostEqual(result.distance_m, 1., places=5)
        self.assertFalse(result.valid_mask[:20].any())
        self.assertAlmostEqual(float(result.xyz[120, 160, 2]), 1., places=5)
        self.assertIsNone(processor.from_disparity(np.zeros_like(disparity)).distance_m)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"cloud.ply"
            write_ply(path, [[0, 0, 1], [float("nan"), 0, 1], [1, 2, 3]])
            content = path.read_text()
            self.assertIn("element vertex 2", content)
            self.assertIn("comment units metre", content)


if __name__ == "__main__":
    unittest.main()

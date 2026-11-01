import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.features import face_features


class FeatureTests(unittest.TestCase):
    def test_fixed_roi_is_used_and_flat_or_outside_inputs_are_invalid(self):
        frame = np.zeros((100, 120), dtype=np.uint8)
        frame[20:60, 40:80] = np.tile(np.arange(40, dtype=np.uint8)*5, (40, 1))
        features = face_features(frame, (40, 20, 40, 40))
        self.assertEqual(features.shape, (1024,))
        self.assertGreater(float(features.std()), .1)
        np.testing.assert_array_equal(frame[0], np.zeros(120, dtype=np.uint8))
        with self.assertRaises(ValueError): face_features(frame, (0, 0, 20, 20))
        with self.assertRaises(ValueError): face_features(frame, (110, 0, 20, 20))


if __name__ == "__main__": unittest.main()

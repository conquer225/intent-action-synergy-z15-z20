import unittest
import numpy as np

from z20_compute.stereo_nominal import fit_nominal_rig


class NominalStereoTests(unittest.TestCase):
    def test_known_two_depth_planes_reconstruct_in_baseline_lengths(self):
        # Independent parallel-camera case: focal200px, baseline1;
        # right shift100px means Z=2, shift50px means Z=4.
        a = np.array([[x, y] for y in (140., 300.)
                      for x in (100., 160., 220., 280., 340., 400.)])
        b = a.copy()
        b[:6, 0] += 100.
        b[6:, 0] += 50.
        rig = fit_nominal_rig(a, b, (640, 480), focal_px=200.)
        np.testing.assert_allclose(rig.xyz[:, 2], [2.]*6+[4.]*6, atol=.001)
        self.assertTrue(rig.valid_mask.all())
        self.assertEqual(rig.units, 'baseline_lengths')
        self.assertFalse(rig.metric)

    def test_insufficient_or_degenerate_correspondences_are_rejected(self):
        a = np.array([[x, y] for y in (80., 150., 220.) for x in (50., 100., 150., 200.)])
        for points, focal in ((a[:7], 200.), (np.zeros((12, 2)), 200.), (a, float('nan'))):
            with self.subTest(count=len(points), focal=focal):
                with self.assertRaises(ValueError):
                    fit_nominal_rig(points, points+np.array([20., 0]), (320, 240), focal_px=focal)

    def test_textured_pair_with_sixteen_pixel_shift_has_depth_ten(self):
        from z20_compute.stereo_nominal import nominal_dense
        rng = np.random.default_rng(51)
        left = rng.integers(0, 256, (240, 320, 3), dtype=np.uint8)
        right = np.zeros_like(left)
        right[:, 16:] = left[:, :-16]
        a = np.array([[x, y] for y in (50., 120., 190.) for x in (60., 120., 180., 240.)])
        rig = fit_nominal_rig(a, a+np.array([16., 0]), (320, 240), focal_px=160.)
        result = nominal_dense(left, right, rig)
        self.assertGreater(int(result.valid_mask.sum()), 10000)
        self.assertAlmostEqual(float(np.median(result.xyz[result.valid_mask, 2])), 10., delta=.1)
        self.assertTrue(np.isnan(result.xyz[~result.valid_mask]).all())


if __name__ == '__main__':
    unittest.main()

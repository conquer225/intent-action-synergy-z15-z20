"""Quarter-sampled capture is restored from owned memory for photo matching."""
import unittest
import numpy as np
from z20_compute.person_dog_camera_scene import photo_input_rgb


class PhotoInputTests(unittest.TestCase):
    def test_main_view_restores_portrait_ratio_and_rgb_without_the_other_eye(self):
        pixels = np.zeros((180, 320, 3), np.uint8)
        pixels[:, :160] = [3, 7, 11]
        pixels[:, 160:] = [91, 92, 93]
        pixels[179, 159] = [17, 19, 23]
        rgb = photo_input_rgb(pixels)
        self.assertEqual(rgb.shape, (360, 320, 3))
        np.testing.assert_array_equal(rgb[0:2, 0:2], np.full((2, 2, 3), [11, 7, 3]))
        np.testing.assert_array_equal(rgb[-1, -1], [23, 19, 17])
        pixels[:] = 255
        np.testing.assert_array_equal(rgb[-1, -1], [23, 19, 17])
        self.assertTrue(rgb.flags.c_contiguous)

    def test_other_sampling_modes_are_rejected(self):
        with self.assertRaises(ValueError):
            photo_input_rgb(np.zeros((360, 640, 3), np.uint8))


if __name__ == '__main__':
    unittest.main()

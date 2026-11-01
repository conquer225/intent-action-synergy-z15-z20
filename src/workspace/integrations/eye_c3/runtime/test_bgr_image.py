import unittest

import numpy as np
from PIL import Image

from system_hdmi import image_from_bgr, image_to_bgr


class BgrImageTests(unittest.TestCase):
    def test_rgb_colours_match_old_negative_stride_conversion(self):
        random=np.random.default_rng(101010)
        for height,width in ((1,1),(7,13),(216,384)):
            bgr=random.integers(0,256,(height,width,3),dtype=np.uint8)
            actual=image_from_bgr(bgr)
            expected=Image.fromarray(bgr[:,:,::-1])
            self.assertEqual(actual.mode,'RGB')
            self.assertEqual(actual.size,expected.size)
            np.testing.assert_array_equal(np.asarray(actual),np.asarray(expected))

    def test_rgb_to_bgr_matches_old_copy_and_is_writable_and_owned(self):
        rgb=Image.fromarray(np.arange(7*13*3,dtype=np.uint8).reshape((7,13,3)))
        actual=image_to_bgr(rgb)
        np.testing.assert_array_equal(actual,np.asarray(rgb)[:,:,::-1].copy())
        self.assertTrue(actual.flags.c_contiguous)
        self.assertTrue(actual.flags.writeable)
        self.assertTrue(actual.flags.owndata)
        before=rgb.tobytes();actual[:]=0
        self.assertEqual(rgb.tobytes(),before)

    def test_strided_input_and_full_round_trip(self):
        source=np.arange(10*20*3,dtype=np.uint8).reshape((10,20,3))
        for bgr in (source,source[::2,::2],source[::-1],source[:,:,::-1]):
            np.testing.assert_array_equal(image_to_bgr(image_from_bgr(bgr)),bgr)

    def test_input_does_not_alias_result(self):
        source=np.zeros((7,13,3),dtype=np.uint8)
        image=image_from_bgr(source);source[:]=255
        self.assertTrue(np.all(np.asarray(image)==0))


if __name__=='__main__':
    unittest.main()

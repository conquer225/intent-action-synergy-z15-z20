import unittest
import numpy as np
from PIL import Image
from intent_one.hdmi import framebuffer_pixels
class FramebufferTests(unittest.TestCase):
    def test_rgb_pages_and_original_bgr_calibration_have_same_color(self):
        rgb=Image.new('RGB',(1280,720),(255,0,0))
        bgr=np.zeros((720,1280,3),dtype=np.uint8);bgr[:,:,2]=255
        self.assertEqual(framebuffer_pixels(rgb)[0,0].tolist(),[0,0,255])
        self.assertTrue(np.array_equal(framebuffer_pixels(rgb),framebuffer_pixels(bgr)))
if __name__=='__main__':unittest.main()

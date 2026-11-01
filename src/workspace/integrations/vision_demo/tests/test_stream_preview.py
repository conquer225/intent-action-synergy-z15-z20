import unittest,numpy as np
from stream_preview import process
class StreamingPreviewTests(unittest.TestCase):
    def test_reference_uses_previous_histogram_and_preserves_first_frame(self):
        rgb=np.full((8,16,3),16,np.uint8);rgb[:,8:]=32
        first,state=process(rgb,8)
        np.testing.assert_array_equal(first,rgb)
        second,_=process(rgb,8,state)
        self.assertTrue((second[:,:8]==0).all());self.assertTrue((second[:,8:]==255).all())
    def test_motion_trail_colours_match_literal_rtl_case(self):
        black=np.zeros((8,16,3),np.uint8);white=black+255
        _,state=process(black,2);image,state=process(white,2,state)
        np.testing.assert_array_equal(image[0,0],[190,255,255])
        image,_=process(black,2,state);np.testing.assert_array_equal(image[0,0],[63,254,255])

import unittest
import cv2
import numpy as np
from vision_demo.pupil import locate_pupil


class PupilMarkingTests(unittest.TestCase):
    def test_ellipse_center_is_in_original_source_coordinates(self):
        gray=np.full((100,180),180,np.uint8)
        cv2.ellipse(gray,(117,54),(9,7),15,0,360,20,-1)
        cv2.circle(gray,(115,52),1,255,-1)
        result=locate_pupil(gray,(80,30,75,48))
        self.assertTrue(result['valid'],result)
        self.assertAlmostEqual(result['center'][0],117,delta=1)
        self.assertAlmostEqual(result['center'][1],54,delta=1)
        self.assertEqual(result['coordinates'],'source_pixels')

    def test_dark_pupil_separates_from_connected_eyelid_shadow(self):
        gray=np.full((60,100),180,np.uint8)
        gray[:19]=70
        cv2.circle(gray,(50,31),16,70,-1)
        cv2.circle(gray,(50,34),7,20,-1)
        result=locate_pupil(gray,(0,0,100,60))
        self.assertTrue(result['valid'],result)
        self.assertAlmostEqual(result['center'][0],50,delta=1)
        self.assertAlmostEqual(result['center'][1],34,delta=1)

    def test_small_low_contrast_infrared_pupil_has_source_coordinates(self):
        gray=np.full((44,44),70,np.uint8)
        gray[:8]=110
        cv2.ellipse(gray,(22,23),(2,3),0,0,360,57,-1)
        result=locate_pupil(gray,(0,0,44,44))
        self.assertTrue(result['valid'],result)
        self.assertAlmostEqual(result['center'][0],22,delta=1)
        self.assertAlmostEqual(result['center'][1],23,delta=1)

    def test_blank_and_competing_pupils_are_not_reported_as_valid(self):
        gray=np.full((60,100),180,np.uint8)
        self.assertFalse(locate_pupil(gray,(0,0,100,60))['valid'])
        cv2.circle(gray,(30,30),7,10,-1);cv2.circle(gray,(70,30),7,10,-1)
        result=locate_pupil(gray,(0,0,100,60))
        self.assertFalse(result['valid'],result)
        self.assertEqual(result['reason'],'ambiguous')


if __name__=='__main__':unittest.main()

"""Registered photos must be recognized from camera pixels, including perspective."""
import unittest
from pathlib import Path

import cv2
import numpy as np

from z20_compute.tablet_photo import RegisteredPhotos


ROOT=Path(__file__).resolve().parents[1]/'artifacts/person_dog'


class TabletPhotoTests(unittest.TestCase):
    def test_perspective_scaled_and_dimmed_photo_maps_boxes_to_camera(self):
        images=[cv2.imread(str(ROOT/'images'/('scene%d.png'%i))) for i in range(3)]
        matcher=RegisteredPhotos(images)
        src=np.float32([[0,0],[639,0],[639,479],[0,479]])
        dst=np.float32([[90,150],[560,110],[545,550],[75,590]])
        h=cv2.getPerspectiveTransform(src,dst)
        for index,image in enumerate(images):
            camera=cv2.warpPerspective(image,h,(640,720),borderValue=(45,45,45))
            camera=cv2.convertScaleAbs(camera,alpha=.7,beta=15)
            result=matcher.match(camera)
            self.assertEqual(result['scene_id'],index)
            self.assertGreaterEqual(result['inliers'],15)
            corners=cv2.perspectiveTransform(src[None],np.array(result['homography']))[0]
            self.assertLess(float(np.max(np.linalg.norm(corners-dst,axis=1))),8.)

    def test_blank_and_unrelated_pixels_clear_registered_scene(self):
        images=[cv2.imread(str(ROOT/'images'/('scene%d.png'%i))) for i in range(3)]
        matcher=RegisteredPhotos(images)
        self.assertIsNotNone(matcher.match(images[0])['scene_id'])
        for camera in (np.zeros((720,640,3),np.uint8),
                       np.random.default_rng(10).integers(0,256,(720,640,3),dtype=np.uint8)):
            result=matcher.match(camera)
            self.assertIsNone(result['scene_id'])
            self.assertIsNone(result['homography'])

import unittest
import json
from pathlib import Path
import numpy as np

from z20_compute.person_dog_camera_scene import project_boxes,camera_scene


class CameraSceneTests(unittest.TestCase):
    def test_reviewed_boxes_follow_measured_homography(self):
        boxes=dict(person=[10,20,30,40],dog=[50,60,80,90])
        h=[[2,0,5],[0,2,7],[0,0,1]]
        self.assertEqual(project_boxes(boxes,h,(200,200)),
                         [[25.,47.,65.,87.],[105.,127.,165.,187.]])

    def test_degenerate_projection_cannot_publish_distance_overlay(self):
        boxes=dict(person=[10,20,30,40],dog=[50,60,80,90])
        for h in (np.zeros((3,3)),np.full((3,3),float('nan'))):
            with self.assertRaises(ValueError):project_boxes(boxes,h,(200,200))

    def test_expired_capture_clears_a_correct_but_old_photo_match(self):
        class Matcher:
            def match(self,rgb):return dict(scene_id=0,homography=np.eye(3).tolist(),inliers=100)
        path=Path(__file__).resolve().parents[1]/'artifacts/person_dog/gallery.json'
        entries=json.loads(path.read_text(encoding='utf-8'))['images']
        result=camera_scene(np.zeros((480,640,3),np.uint8),Matcher(),entries,
                            captured_ns=1_000_000_000,now_ns=lambda:3_100_000_000)
        self.assertIsNone(result['scene'])
        self.assertIsNone(result['match']['scene_id'])
        self.assertEqual(result['match']['state'],'expired_capture')

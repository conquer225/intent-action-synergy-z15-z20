import importlib.util
import unittest
import numpy as np
from z20_compute.cloud import register_open3d


@unittest.skipUnless(importlib.util.find_spec('open3d'), 'run in PC Open3D environment')
class CloudICPTests(unittest.TestCase):
    def test_overlapping_views_recover_known_pose_and_reject_disjoint_view(self):
        world=np.random.RandomState(8).uniform([-.3,-.2,.7],[.3,.2,1.3],(2000,3))
        angle=np.deg2rad(2.)
        rotation=np.array([[np.cos(angle),-np.sin(angle),0],
                           [np.sin(angle),np.cos(angle),0],[0,0,1.]])
        translation=np.array([.04,-.02,.01])
        camera=(world-translation)@rotation
        guess=np.eye(4);guess[:3,:3]=rotation;guess[:3,3]=translation+[.003,-.002,.001]
        poses,reports=register_open3d([world,camera],[np.eye(4),guess],voxel_m=.001)
        np.testing.assert_allclose(poses[1][:3,:3],rotation,atol=1e-4)
        np.testing.assert_allclose(poses[1][:3,3],translation,atol=1e-4)
        self.assertGreater(reports[0]['fitness'],.99)
        self.assertLess(reports[0]['rmse_m'],.0001)
        with self.assertRaises(ValueError):
            register_open3d([world,world+[5,0,0]],[np.eye(4),np.eye(4)],voxel_m=.001)


if __name__=='__main__':unittest.main()

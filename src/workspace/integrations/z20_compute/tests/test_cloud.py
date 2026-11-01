import unittest
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.cloud import fuse_clouds


class CloudTests(unittest.TestCase):
    def test_camera_to_world_poses_and_voxel_merge_keep_metre_scale(self):
        points = np.array([[0, 0, 1.], [.1, 0, 1], [0, .1, 1]])
        second = points-[.2, 0, 0]
        pose = np.eye(4); pose[0, 3] = .2
        result = fuse_clouds([points, second], [np.eye(4), pose], voxel_m=.01)
        self.assertEqual(len(result), 3)
        self.assertTrue(np.allclose(result[:, 2], 1.))
        pose[0, 0] = 2
        with self.assertRaisesRegex(ValueError, "rigid"):
            fuse_clouds([points, second], [np.eye(4), pose])


if __name__ == "__main__": unittest.main()

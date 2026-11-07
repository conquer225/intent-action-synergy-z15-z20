"""Worked point projection, depth and trajectory rendering contracts."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/workspace/integrations'))
from pl_accel.mapping import MapScene, render_reference


class MapRaster(unittest.TestCase):
    def test_depth_test_and_reject_behind_camera(self):
        scene = MapScene([[0, 0, 2], [0, 0, 1], [0, 0, -1]],
                         colors=[[255, 0, 0], [0, 255, 0], [0, 0, 255]],
                         width=9, height=9, focal=4, center=(4, 4))
        rgb, stats = render_reference(scene)
        np.testing.assert_array_equal(rgb[4, 4], [0, 255, 0])
        self.assertEqual(stats['visible_points'], 2)
        self.assertEqual(stats['clipped_points'], 1)

    def test_projected_point_and_bounded_trajectory(self):
        scene = MapScene([[1, 0, 2]], colors=[[17, 34, 51]],
                         trajectory=[[-2, 0, 1], [2, 0, 1]],
                         width=9, height=9, focal=4, center=(4, 4))
        rgb, stats = render_reference(scene)
        # The horizontal trajectory clips to the full row and overlays the point.
        np.testing.assert_array_equal(rgb[4, :, :], np.tile([255, 196, 64], (9, 1)))
        self.assertEqual(stats['trajectory_segments'], 1)

    def test_scene_preserves_units_and_rejects_nonfinite_coordinates(self):
        scene = MapScene([[0, 0, 1]], units='relative_depth_median', frame_id='camera:17')
        self.assertEqual(scene.metadata['units'], 'relative_depth_median')
        self.assertEqual(scene.metadata['frame_id'], 'camera:17')
        with self.assertRaises(ValueError):
            MapScene([[float('nan'), 0, 1]])


if __name__ == '__main__':
    unittest.main()

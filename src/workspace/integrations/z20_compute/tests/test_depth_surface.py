import unittest
import tempfile
import json
from pathlib import Path
import numpy as np

from z20_compute.depth_surface import depth_surface


class DepthSurfaceTests(unittest.TestCase):
    def test_stream_frame_exports_sequence_and_depth_provenance(self):
        from z20_compute.mono_depth import process_monocular_frame
        bgr = np.zeros((4, 4, 3), np.uint8)
        def infer(image):
            self.assertEqual(image.shape, bgr.shape)
            return np.ones((4, 4), np.float32), {'model': 'independent_fixture'}
        with tempfile.TemporaryDirectory() as directory:
            record = process_monocular_frame(23, bgr, directory, infer=infer, focal_px=4.)
            self.assertEqual(record['sequence'], 23)
            self.assertTrue(record['valid'])
            self.assertEqual(record['depth_source'], 'monocular_model_prediction')
            saved = json.loads((Path(directory)/'latest.json').read_text())
            self.assertEqual(saved['sequence'], 23)
            self.assertTrue((Path(directory)/saved['frame_directory']/'surface.ply').exists())

    def test_monocular_export_preserves_raw_depth_but_labels_relative_geometry(self):
        from z20_compute.mono_depth import export_monocular_preview
        bgr = np.zeros((4, 4, 3), np.uint8)
        depth = np.full((4, 4), 4., np.float32)
        with tempfile.TemporaryDirectory() as directory:
            record = export_monocular_preview(bgr, depth, directory, focal_px=4.,
                                               model_name='test_prediction', stride=1)
            self.assertFalse(record['metric_verified'])
            self.assertEqual(record['coordinate_units'], 'relative_depth_median')
            np.testing.assert_array_equal(np.load(Path(directory)/'depth-raw.npy'), depth)
            np.testing.assert_array_equal(np.load(Path(directory)/'depth-relative.npy'), 1.)
            saved = json.loads((Path(directory)/'result.json').read_text())
            self.assertEqual(saved['depth_source'], 'monocular_model_prediction')
            self.assertEqual(saved['triangles'], 18)

    def test_known_plane_backprojects_pixels_and_keeps_rgb(self):
        depth = np.full((3, 3), 2., np.float32)
        bgr = np.zeros((3, 3, 3), np.uint8)
        bgr[:] = [10, 20, 30]
        K = np.array([[2., 0, 1], [0, 2., 1], [0, 0, 1]])
        surface = depth_surface(depth, bgr, K)
        np.testing.assert_allclose(surface.vertices[0], [-1, -1, 2])
        np.testing.assert_allclose(surface.vertices[4], [0, 0, 2])
        np.testing.assert_array_equal(surface.colors[0], [30, 20, 10])
        self.assertEqual(surface.faces.shape, (8, 3))

    def test_mesh_never_bridges_depth_jump_or_invalid_hole(self):
        depth = np.ones((4, 4), np.float32)
        depth[:, 2:] = 3.
        depth[0, 0] = np.nan
        K = np.array([[4., 0, 1.5], [0, 4., 1.5], [0, 0, 1]])
        surface = depth_surface(depth, np.zeros((4, 4, 3), np.uint8), K)
        self.assertTrue(np.isfinite(surface.vertices).all())
        self.assertGreater(len(surface.faces), 0)
        for triangle in surface.vertices[surface.faces]:
            self.assertEqual(float(np.ptp(triangle[:, 2])), 0.)


if __name__ == '__main__':
    unittest.main()

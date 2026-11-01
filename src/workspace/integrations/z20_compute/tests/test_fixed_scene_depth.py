"""Metric geometry under explicitly recorded reference-size assumptions."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from z20_compute.fixed_scene_depth import estimate_geometry


def worked_annotation():
    return dict(person=[300, 220, 340, 260], dog=[360, 220, 400, 260],
                interaction='holding', depth_reference=dict(
                    source='size_prior', focal_length_px=100.,
                    principal_point_px=[320., 240.],
                    person=dict(segment_px=[[310, 100], [310, 200]], length_m=1.,
                                part='worked reference'),
                    dog=dict(segment_px=[[370, 100], [370, 200]], length_m=5.,
                             part='worked reference')))


class FixedSceneDepthTests(unittest.TestCase):
    def test_independent_three_four_five_geometry(self):
        geometry = estimate_geometry(worked_annotation(), (640, 480))
        self.assertEqual(geometry['person_xyz_m'], [0., 0., 1.])
        self.assertEqual(geometry['dog_xyz_m'], [3., 0., 5.])
        self.assertEqual(geometry['distance_m'], 5.)
        self.assertEqual(geometry['status'], 'estimated')
        self.assertEqual(geometry['reference_source'], 'size_prior')

    def test_physical_reference_scale_controls_metric_result(self):
        annotation = worked_annotation()
        original = estimate_geometry(annotation, (640, 480))
        for label in ('person', 'dog'):
            annotation['depth_reference'][label]['length_m'] *= 2
        scaled = estimate_geometry(annotation, (640, 480))
        self.assertEqual(scaled['distance_m'], 2 * original['distance_m'])
        self.assertEqual(scaled['person_depth_m'], 2 * original['person_depth_m'])
        self.assertEqual(scaled['dog_depth_m'], 2 * original['dog_depth_m'])

    def test_missing_scale_keeps_distance_unavailable(self):
        annotation = worked_annotation()
        annotation.pop('depth_reference')
        self.assertIsNone(estimate_geometry(annotation, (640, 480)))

    def test_scene_description_carries_computed_geometry(self):
        from z20_compute.fixed_scene import describe_scene
        self.assertEqual(describe_scene(worked_annotation(), (640, 480))
                         ['geometry']['distance_m'], 5.)

    def test_board_geometry_follows_inferred_pixels_and_clears_for_unknown(self):
        from z20_compute.fixed_scene_package import build_package, BoardSceneBundle
        root = Path(__file__).resolve().parents[1] / 'artifacts' / 'person_dog'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_package(root, output)
            expected = BoardSceneBundle(output).evaluate(2)['geometry']
            self.assertEqual(expected['status'], 'estimated')
            manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
            input_path = output / 'input_0.rgb'
            for raw in ((output / 'input_2.rgb').read_bytes(), bytes(640 * 480 * 3)):
                input_path.write_bytes(raw)
                manifest['files']['input_0.rgb'] = hashlib.sha256(raw).hexdigest()
                (output / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
                result = BoardSceneBundle(output).evaluate(0)
                if any(raw):
                    self.assertEqual(result['scene_id'], 2)
                    self.assertEqual(result['geometry'], expected)
                else:
                    self.assertIsNone(result['scene_id'])
                    self.assertIsNone(result['geometry'])

    def test_desktop_exports_geometry_for_each_registered_scene(self):
        from z20_compute.fixed_scene_demo import SceneDemo, export
        root = Path(__file__).resolve().parents[1] / 'artifacts' / 'person_dog'
        with tempfile.TemporaryDirectory() as directory:
            report = export(SceneDemo(root), directory)
        self.assertEqual([r['geometry']['status'] for r in report['results']],
                         ['estimated'] * 3)
        self.assertTrue(all(r['geometry']['distance_m'] > 0 for r in report['results']))

    def test_degenerate_nonfinite_and_outside_references_are_rejected(self):
        for change in ('zero_segment', 'negative_length', 'nan_length',
                       'infinite_focal', 'outside_pixel', 'unlabelled_source'):
            annotation = copy.deepcopy(worked_annotation())
            reference = annotation['depth_reference']
            if change == 'zero_segment':
                reference['dog']['segment_px'][1] = [370, 100]
            elif change == 'negative_length':
                reference['dog']['length_m'] = -1
            elif change == 'nan_length':
                reference['dog']['length_m'] = float('nan')
            elif change == 'infinite_focal':
                reference['focal_length_px'] = float('inf')
            elif change == 'outside_pixel':
                reference['dog']['segment_px'][0] = [-1, 100]
            else:
                reference.pop('source')
            with self.subTest(change=change), self.assertRaises(ValueError):
                estimate_geometry(annotation, (640, 480))


if __name__ == '__main__':
    unittest.main()

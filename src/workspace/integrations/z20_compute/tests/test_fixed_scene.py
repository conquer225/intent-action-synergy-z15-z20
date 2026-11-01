"""Public fixed-scene recognition and annotation contract."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from z20_compute.fixed_scene import FixedSceneMemory, describe_scene


def example_image(column):
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    image[80:400, column:column + 100] = (220, 140, 40)
    return image


class FixedSceneTests(unittest.TestCase):
    def setUp(self):
        self.images = [example_image(x) for x in (40, 250, 490)]

    def test_pixels_select_registered_scene_after_reordering(self):
        memory = FixedSceneMemory.remember(self.images)
        self.assertEqual([memory.recognize(self.images[i]).scene_id for i in (2, 0, 1)],
                         [2, 0, 1])
        self.assertIsNone(memory.recognize(np.full((480, 640, 3), 127, np.uint8)).scene_id)

    def test_saved_memory_has_same_results_and_uses_backend(self):
        memory = FixedSceneMemory.remember(self.images)

        class Backend:
            name = 'test_npu'
            def infer(self, model, values):
                return model.infer(values)

        with tempfile.TemporaryDirectory() as directory:
            memory.save(directory)
            loaded = FixedSceneMemory.load(directory)
            for image in self.images:
                reference = memory.recognize(image)
                board = loaded.recognize(image, backend=Backend())
                self.assertEqual(board.scene_id, reference.scene_id)
                np.testing.assert_array_equal(board.scores, reference.scores)
                self.assertEqual(board.backend, 'test_npu')

    def test_left_right_comes_from_boxes_not_scene_number(self):
        annotation = dict(person=[30, 20, 110, 240], dog=[180, 90, 310, 260],
                          interaction='holding')
        self.assertEqual(describe_scene(annotation, (640, 480))['position'], 'person_left_of_dog')
        annotation['person'], annotation['dog'] = annotation['dog'], annotation['person']
        self.assertEqual(describe_scene(annotation, (640, 480))['position'], 'person_right_of_dog')
        annotation['person'] = [30, 10, 110, 250]
        self.assertEqual(describe_scene(annotation, (640, 480))['position'], 'same_horizontal_position')

    def test_invalid_boxes_and_unknown_relation_are_rejected(self):
        annotation = dict(person=[-1, 0, 10, 20], dog=[100, 20, 200, 100],
                          interaction='petting')
        with self.assertRaises(ValueError):
            describe_scene(annotation, (640, 480))
        annotation['person'] = [0, 0, 10, 20]
        annotation['interaction'] = 'unknown'
        with self.assertRaises(ValueError):
            describe_scene(annotation, (640, 480))

    def test_real_gallery_recalls_three_interactions_and_exports_frames(self):
        from z20_compute.fixed_scene_demo import SceneDemo, export
        root = Path(__file__).resolve().parents[1] / 'artifacts' / 'person_dog'
        demo = SceneDemo(root)
        with tempfile.TemporaryDirectory() as directory:
            report = export(demo, directory)
            self.assertEqual([r['interaction'] for r in report['results']],
                             ['holding', 'petting', 'leashing'])
            self.assertEqual([r['scene_id'] for r in report['results']], [0, 1, 2])
            self.assertEqual(report['results'][2]['position'], 'person_right_of_dog')
            self.assertEqual(len(list(Path(directory).glob('preview_*.png'))), 3)

    def test_board_bundle_infers_from_raw_pixels_and_detects_tampering(self):
        from z20_compute.fixed_scene_package import build_package, BoardSceneBundle
        root = Path(__file__).resolve().parents[1] / 'artifacts' / 'person_dog'
        with tempfile.TemporaryDirectory() as directory:
            build_package(root, directory)
            bundle = BoardSceneBundle(directory)
            self.assertEqual(bundle.evaluate(2)['interaction'], 'leashing')
            self.assertEqual(bundle.evaluate(0)['position'], 'person_left_of_dog')
            raw = Path(directory) / 'input_0.rgb'
            raw.write_bytes(bytes(len(raw.read_bytes())))
            with self.assertRaisesRegex(ValueError, 'hash'):
                BoardSceneBundle(directory)

    def test_hdmi_plan_matches_vendor_720p_timing_and_static_video_ring(self):
        from z20_compute.fixed_scene_hdmi import display_plan
        plan = display_plan()
        self.assertEqual(plan['frame_bytes'], 1280 * 720 * 3)
        self.assertEqual(plan['addresses'], (0x01000000, 0x01000000 + 2764800,
                                              0x01000000 + 2 * 2764800))
        self.assertEqual(plan['vtc'][0x70], 1650)
        self.assertEqual(plan['vtc'][0x74], (750 << 16) | 750)
        self.assertEqual(plan['vtc'][0x60], (720 << 16) | 1280)
        self.assertEqual(plan['vdma'][0x58], 3840)
        self.assertEqual(plan['vdma'][0x54], 3840)
        self.assertEqual(plan['vdma'][0x50], 720)

    def test_hdmi_enables_vtc_before_starting_display_vdma(self):
        from z20_compute import fixed_scene_hdmi as module
        control, vtc = object(), object()
        display = module.NavigatorHDMI.__new__(module.NavigatorHDMI)
        display.control, display.vtc = control, vtc
        registers, writes = {}, []

        display.video = bytearray(3 * module.FRAME_BYTES)

        def read(mapping, offset):
            return registers.get((mapping, offset), 0)

        def write(mapping, offset, value):
            writes.append((mapping, offset, value))
            registers[mapping, offset] = (0 if mapping is control and
                                          (offset == 0x20004 or value == 4) else value)

        with patch.object(module, '_read', read), patch.object(module, '_write', write):
            display.show(bytes(module.FRAME_BYTES))
        vtc_started = writes.index((vtc, 0, module.display_plan()['vtc_control']))
        vdma_started = writes.index((control, 0x20000,
                                     module.display_plan()['vdma_control']))
        self.assertLess(vtc_started, vdma_started)

    def test_hdmi_registers_require_aligned_32_bit_access(self):
        from z20_compute.fixed_scene_hdmi import _read, _write
        registers = bytearray(8)
        _write(registers, 0, 0x12345678)
        self.assertEqual(_read(registers, 0), 0x12345678)
        with self.assertRaisesRegex(ValueError, 'aligned'):
            _write(registers, 1, 0xabcdef01)

    def test_board_runner_outputs_inferred_annotation_in_software_mode(self):
        from z20_compute.fixed_scene_package import build_package
        from z20_compute.fixed_scene_board import main
        root = Path(__file__).resolve().parents[1] / 'artifacts' / 'person_dog'
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / 'package'
            build_package(root, package)
            report_path = Path(directory) / 'result.json'
            main(['--bundle', str(package), '--backend', 'ps', '--index', '1',
                  '--once', '--output', str(report_path)])
            import json
            report = json.loads(report_path.read_text(encoding='utf-8'))
            self.assertEqual(report['results'][0]['scene_id'], 1)
            self.assertEqual(report['results'][0]['interaction'], 'petting')
            self.assertFalse(report['pl_executed'])

    def test_ps_keys_emit_one_navigation_event_per_stable_press(self):
        from z20_compute.fixed_scene_keys import KeyDebouncer
        keys = KeyDebouncer(stable_seconds=.05)
        self.assertEqual(keys.update(False, False, 0.00), 0)
        self.assertEqual(keys.update(False, True, 0.01), 0)
        self.assertEqual(keys.update(False, False, 0.02), 0)
        self.assertEqual(keys.update(False, True, 0.10), 0)
        self.assertEqual(keys.update(False, True, 0.16), 1)
        self.assertEqual(keys.update(False, True, 0.50), 0)
        self.assertEqual(keys.update(False, False, 0.60), 0)
        self.assertEqual(keys.update(False, False, 0.66), 0)
        self.assertEqual(keys.update(True, False, 0.70), 0)
        self.assertEqual(keys.update(True, False, 0.76), -1)

    def test_release_hash_manifest_stays_valid_after_rebuild(self):
        import hashlib
        import json
        from build_fixed_scene_board import write_sha256_manifest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scene.rgb').write_bytes(b'example RGB bytes')
            write_sha256_manifest(root)
            write_sha256_manifest(root)
            checksums = json.loads((root / 'SHA256.json').read_text(encoding='utf-8'))
            self.assertEqual(checksums, {
                'scene.rgb': hashlib.sha256(b'example RGB bytes').hexdigest()})


if __name__ == '__main__':
    unittest.main()

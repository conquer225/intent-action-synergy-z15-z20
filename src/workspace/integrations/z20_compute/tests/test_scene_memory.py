import tempfile
import unittest
from pathlib import Path

import numpy as np

from z20_compute.scene_memory import SceneRecognizer, TemplateMemory, unit_pixels, horizontal_relation


class SceneMemoryTests(unittest.TestCase):
    def test_position_uses_box_centres_and_changes_when_order_changes(self):
        self.assertEqual(horizontal_relation([10, 10, 30, 90], [70, 20, 90, 60]), 'dog_right_of_person')
        self.assertEqual(horizontal_relation([70, 10, 90, 90], [10, 20, 30, 60]), 'dog_left_of_person')

    def test_three_scene_templates_recall_after_order_changes(self):
        images = []
        for index in range(3):
            image = np.full((64, 96, 3), 20, dtype=np.uint8)
            image[:, 5 + 28 * index:20 + 28 * index] = 220
            images.append(image)
        memory = TemplateMemory.remember([unit_pixels(image) for image in images])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'model.npz'
            memory.save(path)
            loaded = TemplateMemory.load(path)
            self.assertEqual([int(np.argmax(loaded.scores(unit_pixels(images[i])))) for i in (2, 0, 1)], [2, 0, 1])

    def test_blank_input_clears_scene_and_relations(self):
        # No prior inference is needed to reject pixels without information.
        with tempfile.TemporaryDirectory() as directory:
            import json
            root = Path(directory)
            vectors = np.zeros((3, 1024))
            vectors[0, 0], vectors[1, 1], vectors[2, 2] = 1, 1, 1
            TemplateMemory.remember(vectors).save(root / 'scene.npz')
            (root / 'scenes.json').write_text(json.dumps({'scenes': [], 'minimum_score': 30, 'minimum_margin': 10}))
            result = SceneRecognizer(root).infer(np.zeros((480, 640, 3), dtype=np.uint8))
            self.assertFalse(result['valid'])
            self.assertIsNone(result['scene_id'])
            self.assertEqual(result['objects'], [])
            self.assertEqual(result['relations'], [])


if __name__ == '__main__':
    unittest.main()

"""Fixed gallery memory is inferred from pixels through the shared integer core."""
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from z20_compute.fixed_photo import FixedPhotoMemory


class FixedPhotoTests(unittest.TestCase):
    def setUp(self):
        self.images = []
        for region in ((2, 8), (12, 18), (22, 28)):
            image = np.full((32, 32), 30, dtype=np.uint8)
            image[:, region[0]:region[1]] = 220
            self.images.append(image)

    def test_pixels_determine_class_after_reordering(self):
        memory = FixedPhotoMemory.remember(self.images)
        self.assertEqual([memory.predict(self.images[i]).class_id for i in (2, 0, 1)], [2, 0, 1])
        self.assertEqual(memory.integer.w1.shape, (32, 1024))
        self.assertEqual(memory.integer.w2.shape, (3, 32))

    def test_saved_memory_reloads_same_integer_results(self):
        memory = FixedPhotoMemory.remember(self.images)
        with tempfile.TemporaryDirectory() as directory:
            memory.save(Path(directory))
            loaded = FixedPhotoMemory.load(Path(directory))
            for image in self.images:
                np.testing.assert_array_equal(memory.predict(image).scores, loaded.predict(image).scores)

    def test_indistinguishable_templates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'distinguish'):
            FixedPhotoMemory.remember([self.images[0]] * 3)

    def test_gallery_switches_and_wraps_using_saved_weights(self):
        import json
        from z20_compute.fixed_photo_demo import PhotoDemo
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            FixedPhotoMemory.remember(self.images).save(root / 'model')
            filenames = ['a.png', 'b.png', 'c.png']
            for path, image in zip(filenames, self.images):
                Image.fromarray(image).save(root / path)
            (root / 'gallery.json').write_text(json.dumps({'images': filenames}), encoding='utf-8')
            demo = PhotoDemo(root)
            self.assertEqual(demo.current()[1].class_id, 0)
            demo.step(-1)
            self.assertEqual(demo.current()[1].class_id, 2)
            demo.step(1)
            self.assertEqual(demo.current()[1].class_id, 0)


if __name__ == '__main__':
    unittest.main()

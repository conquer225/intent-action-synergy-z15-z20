import unittest
import numpy as np
import cv2
from vision_demo.processing import ReferenceProcessor


class ImageProcessingTests(unittest.TestCase):
    def test_gray_binary_median_sobel_and_equalization_match_independent_opencv(self):
        rng = np.random.default_rng(7015)
        image = rng.integers(0, 256, (12, 16, 3), dtype=np.uint8)
        # The hardware's explicit integer luminance is also verified with literals.
        gray = ((image[..., 0].astype(np.uint32)*77 + image[..., 1].astype(np.uint32)*150
                 + image[..., 2].astype(np.uint32)*29 + 128) >> 8).astype(np.uint8)
        processor = ReferenceProcessor()
        expected = {
            'gray': gray,
            'binary': cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)[1],
            'median': cv2.medianBlur(gray, 3),
            'sobel': np.clip(np.abs(cv2.Sobel(gray, cv2.CV_16S, 1, 0, borderType=cv2.BORDER_REPLICATE)).astype(np.int32)
                             + np.abs(cv2.Sobel(gray, cv2.CV_16S, 0, 1, borderType=cv2.BORDER_REPLICATE)).astype(np.int32), 0, 255).astype(np.uint8),
            'equalize': cv2.equalizeHist(gray),
        }
        for mode, values in expected.items():
            with self.subTest(mode=mode):
                output = processor.process(image, mode, reset=True)
                np.testing.assert_array_equal(output, np.repeat(values[..., None], 3, axis=2))
        primaries = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]]], dtype=np.uint8)
        np.testing.assert_array_equal(processor.process(primaries, 'gray')[0, :, 0], [77, 149, 29, 255])

    def test_history_reset_prevents_old_trails_and_first_frame_motion(self):
        p = ReferenceProcessor()
        image = np.zeros((12, 16, 3), dtype=np.uint8)
        self.assertEqual(int(p.process(image, 'motion').max()), 0)
        image[3:6, 4:8] = 255
        moved = p.process(image, 'trails')
        self.assertEqual(tuple(moved[4, 5]), (255, 255, 255))
        still = p.process(image, 'trails')
        self.assertGreater(int(still[4, 5, 1]), 63)
        reset = p.process(image, 'trails', reset=True)
        self.assertEqual(tuple(reset[4, 5]), (63, 63, 63))

    def test_bad_modes_and_images_are_rejected(self):
        p = ReferenceProcessor()
        with self.assertRaises(ValueError): p.process(np.zeros((4,4,3), np.uint8), 'unknown')
        with self.assertRaises(ValueError): p.process(np.zeros((4,4), np.uint8), 'gray')

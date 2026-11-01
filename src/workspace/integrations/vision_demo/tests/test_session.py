import unittest
import numpy as np

from vision_demo.session import VisionSession, Frame


class SourceSelectionTests(unittest.TestCase):
    def test_key_cycle_changes_only_pupil_mode_to_tobii(self):
        session = VisionSession()
        self.assertEqual(session.snapshot()['source'], 'ov5640')
        for index in range(1, 10):
            session.next_mode()
            self.assertEqual(session.snapshot()['index'], index)
            self.assertEqual(session.snapshot()['source'], 'tobii' if index == 9 else 'ov5640')
        session.next_mode()
        self.assertEqual(session.snapshot()['index'], 0)

    def test_switch_and_expiry_clear_image_and_reject_old_camera(self):
        session = VisionSession()
        image = np.zeros((8, 10, 3), dtype=np.uint8)
        first = Frame('ov5640', 0, 1, 10.0, image)
        self.assertTrue(session.accept(first, 10.1))
        self.assertIsNotNone(session.current(10.2))
        session.next_mode()
        self.assertIsNone(session.current(10.2))
        self.assertFalse(session.accept(first, 10.2))
        current = Frame('ov5640', session.generation, 2, 10.2, image)
        self.assertTrue(session.accept(current, 10.3))
        self.assertFalse(session.accept(current, 10.4))
        self.assertIsNotNone(session.current(10.5))
        self.assertIsNone(session.current(12.0))
        self.assertFalse(session.accept(Frame('tobii', session.generation, 3, 12.0, image), 12.0))


if __name__ == '__main__':
    unittest.main()

"""Independent sensor/output aspect checks for the portrait stereo halves."""
import unittest

from z20_compute.navigator_camera_geometry import crop_plan


class NavigatorCameraGeometryTests(unittest.TestCase):
    def test_crop_preserves_pixel_aspect_for_640_by_720_output(self):
        plan = crop_plan()
        self.assertEqual(plan['window'], [448, 4, 2176, 1948])
        x0, y0, x1, y1 = plan['window']
        self.assertEqual((x1-x0)*720, (y1-y0)*640)
        self.assertEqual(x0+x1, 2624)
        self.assertEqual(plan['mode'], 'navigator-centered-portrait-640x720-v1')

    def test_window_registers_encode_inclusive_sensor_endpoints(self):
        registers = dict(crop_plan()['registers'])
        def word(address):
            return registers[address]*256+registers[address+1]
        self.assertEqual(word(0x3800), 448)
        self.assertEqual(word(0x3802), 4)
        self.assertEqual(word(0x3804)+1, 2176)
        self.assertEqual(word(0x3806)+1, 1948)
        self.assertTrue(all(0x3800<=address<=0x3807 for address in registers))

    def test_unsupported_or_impossible_output_is_rejected(self):
        for output in ((0,720),(640,-1),(640.5,720),(True,720),(10000,1)):
            with self.subTest(output=output), self.assertRaises(ValueError):
                crop_plan(output=output)

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.calibration_target import a4_checkerboard_svg


class CalibrationTargetTests(unittest.TestCase):
    def test_a4_target_has_measurable_9_by_6_inner_corners(self):
        root = ET.fromstring(a4_checkerboard_svg())
        self.assertEqual(root.attrib["width"], "297mm")
        self.assertEqual(root.attrib["height"], "210mm")
        self.assertEqual(root.attrib["viewBox"], "0 0 297 210")
        black = [node for node in root.iter() if node.tag.endswith("rect")
                 and node.attrib.get("fill") == "black"]
        self.assertEqual(len(black), 35)
        self.assertEqual({float(node.attrib["width"]) for node in black}, {25.0})
        self.assertEqual({float(node.attrib["height"]) for node in black}, {25.0})

        scale = 8
        image = Image.new("L", (297 * scale, 210 * scale), 255)
        draw = ImageDraw.Draw(image)
        for node in black:
            x = float(node.attrib["x"]) * scale
            y = float(node.attrib["y"]) * scale
            draw.rectangle((x, y, x + 25 * scale, y + 25 * scale), fill=0)
        found, corners = cv2.findChessboardCornersSB(np.array(image), (9, 6))
        self.assertTrue(found)
        self.assertEqual(corners.reshape(-1, 2).shape, (54, 2))

    def test_rejects_board_too_large_for_a4_with_margin(self):
        with self.assertRaises(ValueError):
            a4_checkerboard_svg(square_mm=30)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path

from build_camera_demo_dtb import camera_demo_tree


class CameraDemoDTBTests(unittest.TestCase):
    def test_separate_display_is_reserved_without_replacing_camera_or_npu(self):
        root=Path(__file__).resolve().parents[1]
        tree=camera_demo_tree((root/'build/navigator/navigator-stereo.dtb').read_bytes())
        self.assertEqual(list(tree.get_node('/reserved-memory/display@4000000').get_property('reg')),
                         [0x04000000,8294400])
        self.assertIsNotNone(tree.get_node('/reserved-memory/display@4000000').get_property('no-map'))
        self.assertEqual(list(tree.get_node('/video-observer@43c20000').get_property('reg')),
                         [0x43c20000,0x10000,0x01000000,8294400,0x04000000,8294400])
        self.assertEqual(list(tree.get_node('/reserved-memory/npu@2000000').get_property('reg')),
                         [0x02000000,0x100000])

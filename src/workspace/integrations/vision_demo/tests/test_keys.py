import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'ps_tobii/src'))
from vision_demo.keys import VisionKey


class KeySelectionTests(unittest.TestCase):
    def test_only_released_then_debounced_key0_advances(self):
        key=VisionKey(initial=3)
        self.assertFalse(key.feed(2,0.0))
        self.assertTrue(key.feed(2,.06))
        self.assertFalse(key.feed(2,1.0))
        self.assertFalse(key.feed(3,1.1))
        self.assertFalse(key.feed(3,1.2))
        self.assertFalse(key.feed(1,1.3))  # KEY1 does nothing.
        self.assertFalse(key.feed(1,1.4))
        self.assertFalse(key.feed(0,1.5))
        self.assertTrue(key.feed(0,1.6))


if __name__=='__main__':unittest.main()

class SignalKeysTests(unittest.TestCase):
 def test_two_keys_startup_held_and_simultaneous_press_are_suppressed(self):
  from vision_demo.keys import SignalKeys
  keys=SignalKeys(initial=1)
  self.assertIsNone(keys.feed(1,0));self.assertIsNone(keys.feed(1,.1))
  keys.feed(3,.2);keys.feed(3,.3);keys.feed(1,.4)
  self.assertEqual(keys.feed(1,.5),'signal');self.assertIsNone(keys.feed(1,.6))
  keys.feed(3,.7);keys.feed(3,.8);keys.feed(0,.9);self.assertIsNone(keys.feed(0,1))
  self.assertIsNone(keys.feed(2,1.1));self.assertIsNone(keys.feed(2,1.2))
  keys.feed(3,1.3);keys.feed(3,1.4);keys.feed(2,1.5)
  self.assertEqual(keys.feed(2,1.6),'image')

import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from buttons import Edges

class ButtonTests(unittest.TestCase):
    def test_bounce_does_not_start(self):
        e=Edges([103])
        self.assertEqual(e.feed(103,1,1),[])
        e.feed(103,0,1.01);e.feed(103,1,1.02);e.feed(103,0,1.03)
        self.assertEqual(e.advance(2),[])

    def test_short_press_and_hold_only_once(self):
        e=Edges([103])
        e.feed(103,1,1)
        self.assertEqual(e.advance(1.06),[103])
        self.assertEqual(e.feed(103,2,1.2),[])
        self.assertEqual(e.feed(103,1,1.3),[])
        self.assertEqual(e.advance(2),[])

    def test_held_at_start_requires_release(self):
        e=Edges([103],held=[103])
        self.assertEqual(e.feed(103,1,1),[])
        self.assertEqual(e.advance(2),[])
        e.feed(103,0,3);e.advance(3.06)
        e.feed(103,1,4)
        self.assertEqual(e.advance(4.06),[103])

    def test_batched_press_release_keeps_real_short_tap(self):
        e=Edges([103])
        e.feed(103,1,1)
        self.assertEqual(e.feed(103,0,1.15),[103])
        e.advance(1.21);e.feed(103,1,2)
        self.assertEqual(e.advance(2.06),[103])

    def test_two_keys_are_independent(self):
        e=Edges([103,108])
        e.feed(103,1,1);e.feed(108,1,1.01)
        self.assertEqual(e.advance(1.07),[103,108])

if __name__=="__main__":unittest.main()

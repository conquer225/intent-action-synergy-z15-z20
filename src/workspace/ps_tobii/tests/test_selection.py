import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from selection import Selection


class SelectionTests(unittest.TestCase):
    def test_explicit_horizontal_mode_can_confirm_without_vertical_coordinate(self):
        s=Selection()
        events=[dict(valid=True,x=.5,monotonic_ns=round((10+i/60)*1e9)) for i in range(240)]
        self.assertEqual(sum(s.update_horizontal(e,10+i/60) for i,e in enumerate(events)),1)
        normal=Selection()
        self.assertFalse(normal.update(events[0],10))
        self.assertEqual(normal.hover,-1)
        self.assertFalse(s.update_horizontal(dict(valid=True,x=float('nan'),monotonic_ns=14_000_000_000),14))
        self.assertEqual(s.progress,0)

    def gaze(self,s,t,x=.5,valid=True,age=0):
        return s.update(dict(kind="gaze",valid=valid,x=x,y=.65,monotonic_ns=round(t*1e9)),t+age)

    def hold(self,s,start,x,duration=2):
        return sum(self.gaze(s,start+i/60,x) for i in range(round(duration*60)))

    def test_confirm_once_then_change_region(self):
        s=Selection()
        self.assertEqual(self.hold(s,10,.2,4),1)
        self.assertEqual(self.hold(s,14,.2,2),0)
        self.assertEqual(self.hold(s,16,.8,2),1)
        self.assertEqual(self.hold(s,18,.2,2),1)
        self.assertEqual(s.confirmations,3)

    def test_invalid_resets_dwell_but_does_not_rearm_same_region(self):
        s=Selection();self.hold(s,10,.5,1)
        self.gaze(s,11,valid=False)
        self.assertEqual(s.progress,0)
        self.assertEqual(self.hold(s,11.02,.5,1),0)
        self.assertEqual(self.hold(s,12.02,.5,1),1)
        self.gaze(s,13.03,valid=False)
        self.assertEqual(self.hold(s,13.05,.5,2),0)

    def test_stale_gap_pause_and_future_samples_cannot_confirm(self):
        s=Selection();self.hold(s,10,.2,1)
        self.assertFalse(self.gaze(s,11,.2,age=.5))
        self.assertEqual(s.progress,0)
        self.assertEqual(self.hold(s,12,.2,1),0)
        s.toggle_pause()
        self.assertEqual(self.hold(s,13,.2,2),0)
        s.toggle_pause()
        self.assertEqual(self.hold(s,15,.2,1),0)
        self.assertFalse(s.update(dict(valid=True,x=.2,y=.5,monotonic_ns=20_000_000_000),16))
        self.assertEqual(s.progress,0)
        s.view(17)
        self.assertEqual(s.hover,-1)

    def test_boundary_jitter_and_bad_coordinates(self):
        s=Selection()
        for i in range(300):
            self.gaze(s,10+i/60,1/3+(-.01 if i%2 else .01))
        self.assertEqual(s.confirmations,0)
        for i,x in enumerate((float('nan'),float('inf'),-.1,1.1,True)):
            self.assertFalse(self.gaze(s,16+i,x))
        self.assertEqual(s.hover,-1)

    def test_old_duplicate_sample_does_not_advance(self):
        s=Selection();self.hold(s,10,.5,.8)
        before=s.progress
        self.assertFalse(self.gaze(s,10.1,.5))
        self.assertEqual(s.progress,before)


if __name__=="__main__":unittest.main()

import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from tracking import Tracking

class TrackingTests(unittest.TestCase):
    def event(self,**kw):
        return dict(samples=30,left=28,right=20,pupil_left=26,pupil_right=0,distance_mm=606.0,**kw)

    def test_missing_distance_is_unknown_and_never_zero(self):
        t=Tracking();e=self.event();e["distance_mm"]=None
        self.assertTrue(t.update(e,1))
        self.assertIn("距离 未知",t.lines(1)[0])
        self.assertIn("左 87% / 右 0%",t.lines(1)[1])

    def test_old_measurement_expires(self):
        t=Tracking();t.update(self.event(),1)
        self.assertIn("约 60.6 cm",t.lines(2)[0])
        self.assertIn("等待新数据",t.lines(2.6)[0])

    def test_bad_counts_and_nonfinite_distance_cannot_refresh(self):
        t=Tracking()
        for key,value in [("left",31),("samples",0),("right",True),("distance_mm",float('nan')),("distance_mm",0)]:
            e=self.event();e[key]=value
            self.assertFalse(t.update(e,1))
        self.assertIsNone(t.updated)

    def test_valid_detection_is_distinct_from_pupil_measurement(self):
        t=Tracking();t.update(self.event(),1)
        self.assertIn("右眼检测 67%",t.lines(1)[0])
        self.assertIn("右 0%",t.lines(1)[1])

if __name__=='__main__':unittest.main()

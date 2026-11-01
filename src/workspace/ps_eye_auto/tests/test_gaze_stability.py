"""r5 image-sequence regression. Generated eyes are not measured human accuracy."""
import json
import statistics
import unittest
from pathlib import Path
from test_pc_gaze import GazeEngine, calibrated, step
from replay_eye_features import Feature,bind
from pc_model import np,Roi
import ctypes as C


class Stability(unittest.TestCase):
    def setUp(self):
        self.e=GazeEngine()
        calibrated(self.e)

    def tearDown(self):
        self.e.close()

    def test_jitter_median_and_isolated_jump(self):
        e=self.e
        step(e,n=10)
        raw=[];filtered=[]
        for i in range(90):
            dx=(-1,0,1,0,0)[i%5]
            s=step(e,40+dx,120+dx)
            self.assertEqual(s['direction_name'],'CENTER')
            self.assertFalse(s['commit'])
            raw.append(s['gaze_raw']);filtered.append(s['gaze_filtered'])
        self.assertLess(statistics.pstdev(filtered),statistics.pstdev(raw)/2)
        # A single bilateral wrong location must not emit a side or old event.
        s=step(e,60,140)
        self.assertFalse(s['valid']);self.assertEqual(s['event_seq'],0)
        for _ in range(8):
            s=step(e)
            self.assertIn(s['direction_name'],('CENTER','INVALID'))
        self.assertEqual(s['direction_name'],'CENTER')

    def test_fractional_centroid_and_large_roi(self):
        lib=bind(self.e)
        def feature(a):
            h,w=a.shape[:2];r=Roi(0,0,w,h,24,80);f=Feature()
            lib.eye_analyze_rgb888(a.ctypes.data,a.strides[0],w,h,C.byref(r),C.byref(f))
            self.assertTrue(f.valid)
            return f
        a=np.full((64,96,3),160,np.uint8);a[20:34,25:45]=5
        f=feature(a)
        # Geometric rectangle center is 34.5, not its displayed marker at 35.
        self.assertEqual(f.normalized_x,92)
        self.assertEqual(f.x,35)
        big=np.full((3072,4096,3),160,np.uint8);big[320:2752,2304:4000]=5
        f=feature(big)
        self.assertGreaterEqual(f.normalized_x,194)
        self.assertLessEqual(f.normalized_x,199)

    def test_blink_disagreement_and_stale_history(self):
        e=self.e
        step(e,20,100,n=14)
        self.assertEqual(e.state()['event_seq'],1)
        for kwargs in (dict(missing='left'),dict(missing='right'),dict(dark=True),
                       dict(lx=20,rx=140),dict(dt=500),dict(dt=1200)):
            s=step(e,**kwargs)
            self.assertFalse(s['valid']);self.assertFalse(s['commit'])
            self.assertEqual(s['filter_count'],0);self.assertFalse(s['armed'])
            self.assertEqual(s['cal_mask'],7)
            # No stale center history may rearm on the first returning frame.
            self.assertFalse(step(e)['valid'])
        step(e,60,140,n=16)
        self.assertEqual(e.state()['event_seq'],1)
        step(e,n=12)
        self.assertTrue(e.state()['armed'])
        self.assertEqual(step(e,60,140,n=16)['event_seq'],2)

    def test_boundary_and_out_of_range_never_commit(self):
        e=self.e
        for x in [29,30,31]*20:
            s=step(e,x,x+80)
            self.assertFalse(s['valid']);self.assertEqual(s['event_seq'],0)
        # Artificially narrow valid personal range to exercise extrapolation.
        e.reset();step(e,n=2);e.last_sample=__import__('time').monotonic()
        self.assertTrue(e.calibrate())
        for x in (36,40,44):step(e,x,x+80,n=36)
        self.assertEqual(e.state()['cal_mask'],7)
        s=step(e,60,140,n=20)
        self.assertFalse(s['valid']);self.assertEqual(s['tracking_reason'],3)
        self.assertEqual(s['event_seq'],0)

    def test_personal_binocular_scale_and_mirror(self):
        e=self.e
        for mirror in (False,True):
            e.reset();step(e,n=2);e.last_sample=__import__('time').monotonic()
            initial_seq=e.state()['event_seq']
            self.assertTrue(e.calibrate())
            positions=[(28,114),(40,124),(52,134)]
            if mirror:positions.reverse()
            for l,r in positions:step(e,l,r,n=36)
            self.assertEqual(e.state()['cal_mask'],7)
            for i,(l,r) in enumerate(positions):
                s=step(e,l,r,n=16)
                self.assertEqual(s['direction_name'],('LEFT','CENTER','RIGHT')[i])
                self.assertLessEqual(abs(s['gaze_raw']-(-256,0,256)[i]),1)
            self.assertEqual(s['event_seq'],initial_seq+2)

    def test_noisy_calibration_rejected_and_outlier_robust(self):
        e=self.e
        e.reset();step(e,n=2);e.last_sample=__import__('time').monotonic();self.assertTrue(e.calibrate())
        for x in (36,40,44):
            step(e,x,x+80,n=20)
            for i in range(16):
                dx=-2 if i%2 else 2
                step(e,x+dx,x+80+dx)
        self.assertTrue(e.state()['failed']);self.assertEqual(e.state()['cal_mask'],0)
        e.reset();step(e,n=2);e.last_sample=__import__('time').monotonic();self.assertTrue(e.calibrate())
        for x in (20,40,60):
            step(e,x,x+80,n=20)
            for i in range(16):step(e,x+(2 if i==7 else 0),x+80)
        s=e.state();self.assertEqual(s['cal_mask'],7)
        self.assertEqual(s['cal_l_center'],128)
        self.assertEqual(s['cal_l_mad_center'],0)

    def test_switch_latency_and_dwell_at_different_cadences(self):
        rows=[]
        for dt in (33,100,200,250):
            self.e.reset();calibrated(self.e)
            initial_seq=self.e.state()['event_seq']
            step(self.e,n=30,dt=dt)
            elapsed=0;first=None;event=None
            for _ in range(80):
                elapsed+=dt;s=step(self.e,20,100,dt=dt)
                if s['valid'] and first is None:first=elapsed
                if s['commit']:event=elapsed;break
            self.assertIsNotNone(first);self.assertIsNotNone(event)
            self.assertLessEqual(first,1000)
            self.assertGreaterEqual(event-first,750)
            self.assertEqual(s['event_seq'],initial_seq+1)
            rows.append(dict(sample_interval_ms=dt,first_direction_ms=first,event_ms=event))
        self.__class__.cadences=rows


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Stability)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        path=Path(__file__).resolve().parents[1]/'report/stability_sequences_r5.json'
        path.write_text(json.dumps(dict(source='Generated image sequences, not human accuracy',
            tests=result.testsRun,cadences=Stability.cadences),indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())

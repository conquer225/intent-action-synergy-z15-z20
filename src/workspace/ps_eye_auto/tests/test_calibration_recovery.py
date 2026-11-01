"""r6 shared-C regression: generated images, no webcam or human accuracy claim."""
import time
import unittest
from test_pc_gaze import GazeEngine,step,GazeWorker
from pc_gaze import calibration_diagnostic


class CalibrationRecovery(unittest.TestCase):
    def setUp(self):
        self.e=GazeEngine()
        step(self.e,n=2);self.e.last_sample=time.monotonic()
        self.assertTrue(self.e.calibrate())

    def tearDown(self):self.e.close()

    def point(self,x,offsets=None):
        step(self.e,x,x+80,n=20)
        for dx in offsets or [0]*16:step(self.e,x+dx,x+80+dx)
        return self.e.state()

    def test_startup_outlier_and_moderate_jitter_complete(self):
        # Full span is > r5's 18 even without the isolated startup mistake.
        # Core spread is ~22; references remain much farther apart than noise.
        for x in (24,40,56):
            s=self.point(x,[9]+[-3,-2,-1,0,1,2,3,0]*1+[-2,-1,0,1,2,3,0])
        self.assertEqual(s['cal_mask'],7)
        self.assertFalse(s['failed'])
        self.assertLessEqual(abs(s['cal_l_center']-128),3)
        self.assertEqual(step(self.e,24,104,n=16)['direction_name'],'LEFT')

    def test_large_initial_outlier_does_not_poison_point(self):
        s=self.point(20,[25]+[0]*15)
        self.assertEqual((s['stage'],s['cal_mask']),(2,1))
        self.assertEqual(s['cal_l_left'],43)

    def test_unstable_window_rolls_without_clearing_partner(self):
        step(self.e,30,110,n=20)
        for dx in [-10,10]*8:s=step(self.e,30+dx,110)
        self.assertEqual(s['stage'],1)
        self.assertEqual(s['cal_left_count'],16)
        self.assertFalse(s['cal_left_ready'])
        self.assertTrue(s['cal_right_ready'])
        self.assertEqual(s['cal_right_count'],16)
        self.assertFalse(s['valid'])
        s=step(self.e,30,110,n=16)
        self.assertEqual((s['stage'],s['cal_mask']),(2,1))
        self.assertEqual(s['cal_r_left'],85)

    def test_old_three_mad_gate_no_longer_rejects_separated_points(self):
        # ~38-unit gaps exceed 2*MAD sums (32-36), not the r5 gate (48-54).
        for x in (31,40,49):s=self.point(x,[-2,2]*8)
        self.assertEqual(s['cal_mask'],7)
        self.assertFalse(s['failed'])

    def test_overlap_still_rejected_with_preserved_evidence(self):
        for x in (36,40,44):s=self.point(x,[-2,2]*8)
        self.assertTrue(s['failed']);self.assertEqual(s['cal_mask'],0)
        self.assertEqual(s['cal_failure_reason'],3)
        self.assertGreater(s['cal_l_center'],0)
        self.assertGreater(s['cal_l_mad_center'],0)
        self.assertLessEqual(s['cal_failure_gap'],s['cal_failure_noise'])
        self.assertIn('抖动门槛',calibration_diagnostic(s))
        for _ in range(30):
            s=step(self.e)
            self.assertFalse(s['valid']);self.assertFalse(s['commit'])

    def test_retry_preserves_prefix_and_waits_again(self):
        for x in (20,40,40):s=self.point(x)
        self.assertEqual((s['cal_failure_reason'],s['cal_failure_eye'],s['cal_retry_stage']),(1,1,3))
        refs=(s['cal_l_left'],s['cal_l_center'])
        step(self.e,valid=False)
        self.e.last_sample=time.monotonic();self.assertFalse(self.e.calibrate(retry=True))
        # A new pose cannot silently replace the failed calibration anchor.
        s=step(self.e,shift=40,n=3)
        self.assertEqual(s['paused'],16)
        self.assertFalse(self.e.calibrate(retry=True))
        step(self.e,n=2);self.e.last_sample=time.monotonic()
        self.assertTrue(self.e.calibrate(retry=True))
        s=step(self.e,60,140,n=19)
        self.assertEqual((s['stage'],s['cal_mask'],s['cal_left_count']),(3,3,0))
        self.assertEqual((s['cal_l_left'],s['cal_l_center']),refs)
        self.assertEqual(s['cal_l_right'],0)
        s=step(self.e,60,140,n=17)
        self.assertEqual((s['cal_mask'],s['failed']),(7,0))
        self.assertFalse(self.e.calibrate(retry=True))
        self.assertEqual(step(self.e,60,140,n=16)['direction_name'],'RIGHT')

    def test_order_and_other_eye_failure_identified(self):
        for l,r in ((20,100),(40,140),(60,120)):step(self.e,l,r,n=36)
        s=self.e.state()
        self.assertEqual((s['cal_failure_reason'],s['cal_failure_eye'],s['cal_retry_stage']),(2,2,2))
        self.assertIn('画面右眼',calibration_diagnostic(s))
        self.assertIn('中点不在',calibration_diagnostic(s))

    def test_failure_ui_retry_and_fixed_geometry(self):
        import tkinter as tk
        import queue
        from test_pc_gaze import GazePreview,eye_frame,result_for
        class Worker:
            epoch=0
            def __init__(self):self.results=queue.Queue();self.commands=[]
            def request(self,*args):self.epoch+=1;self.commands.append(args)
            def close(self):pass
        for x in (20,40,40):self.point(x)
        worker=Worker();root=tk.Tk();app=GazePreview(root,worker)
        try:
            root.update();height=app.canvas.winfo_height();app.running=True
            app.apply_result(dict(state='camera',frame=eye_frame(),raw=eye_frame(),result=result_for(self.e)))
            root.update()
            self.assertEqual(app.canvas.winfo_height(),height)
            self.assertEqual(worker.commands,[])
            self.assertEqual(app.calibrate_button['text'],'重采失败点')
            self.assertIn('间距 0',app.status.get())
            self.assertIn('参考',app.eye_details.get())
            app.calibrate()
            self.assertEqual(worker.commands,[('retry',)])
        finally:app.close()

    def test_failure_transition_export_captures_references_immediately(self):
        for x in (20,40,40):s=self.point(x)
        # Call trace on a lightweight object: no camera or worker needed.
        from collections import deque
        worker=object.__new__(GazeWorker)
        worker.history=deque(maxlen=2000);worker.history_id=0;worker.previous=None
        worker.last_trace=time.monotonic()
        worker.trace(dict(gaze=s,host_ms=20,period_ms=100,width=160,height=80))
        entry=worker.history[-1]
        self.assertEqual(entry['kind'],'state')
        self.assertEqual(entry['gaze']['cal_l_center'],s['cal_l_center'])
        self.assertIn('间距 0',entry['text'])


if __name__=='__main__':unittest.main(verbosity=2)

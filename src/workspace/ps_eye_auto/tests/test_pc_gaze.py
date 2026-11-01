"""Native gaze, worker and Tk integration. Cameras are mocked; never opened."""
import ctypes as C
import json
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pc_model import Box,Roi,Loc,np,cv2,load_image
from pc_gaze import GazeEngine,annotate_gaze
from pc_gaze_preview import GazeWorker,GazePreview

def eye_frame(lx=40,rx=120,dark=False):
    frame=np.full((80,160,3),0 if dark else 160,np.uint8)
    if not dark:
        for x in (lx,rx):frame[28:36,x-4:x+5]=5
    return frame

def location(valid=True,shift=0):
    return Loc(Box(shift,0,150,80,1),Roi(10,10,60,50,24,80),Roi(90,10,60,50,24,80),int(valid),int(valid),2*int(valid))

def step(engine,lx=40,rx=120,n=1,dt=100,valid=True,shift=0,dark=False,detect=20,missing=None):
    for _ in range(n):
        frame=eye_frame(lx,rx,dark);loc=location(valid,shift)
        if missing=='left':frame[:,10:70]=160
        if missing=='right':frame[:,90:150]=160
        engine.lib.pc_gaze_step(engine.context,frame.ctypes.data,frame.strides[0],160,80,C.byref(loc),dt,detect)
    return engine.state()

def calibrated(engine,mirror=False):
    step(engine,n=2);engine.last_sample=time.monotonic()
    assert engine.calibrate()
    for x in ([60,40,20] if mirror else [20,40,60]):step(engine,x,x+80,n=36)
    assert engine.state()['cal_mask']==7

def result_for(engine,**changes):
    s=engine.state();s.update(changes)
    return dict(valid=True,faces=1,eye_count=2,face=[0,0,150,80],gaze=s,
                host_ms=20.,period_ms=100,width=160,height=80,sampled=time.monotonic())

class Native(unittest.TestCase):
    def setUp(self):self.engine=GazeEngine()
    def tearDown(self):self.engine.close()

    def test_three_points_dwell_rearm_and_mirror(self):
        self.assertFalse(self.engine.calibrate())
        calibrated(self.engine)
        s=step(self.engine,20,100,n=14)
        self.assertEqual((s['direction_name'],s['event_seq'],s['armed']),('LEFT',1,0))
        self.assertEqual(step(self.engine,20,100,n=30)['event_seq'],1)
        self.assertFalse(step(self.engine,20,140)['valid'])
        self.assertEqual(step(self.engine,60,140,n=10)['event_seq'],1)
        self.assertEqual(step(self.engine,40,120,n=10)['direction_name'],'CENTER')
        s=step(self.engine,60,140,n=14)
        self.assertEqual((s['direction_name'],s['event_seq']),('RIGHT',2))
        self.engine.reset();calibrated(self.engine,mirror=True)
        self.assertEqual(step(self.engine,60,140,n=14)['direction_name'],'LEFT')

    def test_invalid_pose_loss_slow_and_calibration_failures(self):
        calibrated(self.engine)
        self.assertFalse(step(self.engine,dark=True)['valid'])
        s=step(self.engine,shift=40)
        self.assertEqual(s['cal_mask'],7);self.assertFalse(s['valid']);self.assertEqual(s['paused'],16)
        self.assertEqual(step(self.engine,valid=False)['cal_mask'],7)
        self.assertEqual(step(self.engine,n=5)['direction_name'],'CENTER')
        self.assertFalse(step(self.engine,dt=1200)['valid'])
        self.assertFalse(step(self.engine,detect=1200)['valid'])
        self.engine.reset();step(self.engine,n=2);self.engine.last_sample=time.monotonic()
        self.assertTrue(self.engine.calibrate())
        s=step(self.engine,n=108)
        self.assertTrue(s['failed']);self.assertEqual(s['cal_mask'],0)
        step(self.engine,n=2);self.engine.last_sample=time.monotonic();self.assertTrue(self.engine.calibrate())
        s=step(self.engine,n=151,dark=True)
        self.assertFalse(s['failed']);self.assertEqual(s['stage'],1)

    def test_resume_partial_points_alternating_eyes_and_pose(self):
        e=self.engine
        step(e,n=2,missing='right');e.last_sample=time.monotonic()
        self.assertTrue(e.calibrate())  # Stable model pair plus one usable feature.
        step(e,20,100,n=36)
        s=step(e,n=25)
        self.assertEqual((s['cal_mask'],s['stage'],s['cal_left_count'],s['cal_right_count']),(1,2,5,5))
        for kwargs in (dict(valid=False,n=20),dict(shift=40,n=5),dict(dt=1200),dict(detect=1200),dict(dark=True,n=200)):
            s=step(e,**kwargs)
            self.assertEqual((s['cal_mask'],s['stage'],s['cal_left_count'],s['cal_right_count']),(1,2,5,5))
            self.assertFalse(s['valid']);self.assertFalse(s['commit']);self.assertFalse(s['failed'])
        step(e,n=11)
        self.assertEqual(e.state()['stage'],3)
        step(e,60,140,n=20)
        for i in range(32):
            s=step(e,60,140,missing='left' if i%2 else 'right')
            self.assertFalse(s['commit']);self.assertFalse(s['valid'])
        self.assertEqual((s['stage'],s['cal_mask']),(0,7))
        s=step(e,20,100,n=14)
        self.assertEqual(s['event_seq'],1)
        s=step(e,n=20,missing='right')
        self.assertFalse(s['valid']);self.assertFalse(s['armed']);self.assertEqual(s['cal_mask'],7)
        self.assertEqual(step(e,60,140,n=10)['event_seq'],1)
        step(e,n=10)
        self.assertEqual(step(e,60,140,n=14)['event_seq'],2)

    def test_fresh_calibration_and_real_localization(self):
        step(self.engine,n=2);self.engine.last_sample=time.monotonic()-2
        self.assertFalse(self.engine.calibrate())
        frame=eye_frame();unchanged=frame.copy()
        r=self.engine.process(frame)
        self.assertFalse(r['valid']);self.assertFalse(r['gaze']['valid'])
        self.assertTrue(np.array_equal(frame,unchanged))
        path=ROOT.parent/'local/eye_captures/auto_replay/inputs/raw.png'
        if path.exists():
            frame=load_image(path);unchanged=frame.copy()
            r=self.engine.process(frame);r=self.engine.process(frame)
            self.assertTrue(r['valid']);self.assertEqual(r['gaze']['stable'],2)
            self.assertEqual(r['gaze']['cal_mask'],0)
            self.assertFalse(r['gaze']['valid'])
            self.assertTrue(np.array_equal(frame,unchanged))
            self.assertEqual(annotate_gaze(frame,r).shape,frame.shape)
            # r2 retains a valid partner and all measured rejection diagnostics.
            self.assertTrue(r['gaze']['left_valid'])
            self.assertGreater(r['gaze']['left_selected'],0)
            self.assertGreater(r['gaze']['right_reason'],0)

    def test_head_motion_preserves_calibration_and_gaze(self):
        e=self.engine
        def observe(offset=0,dx=0,dy=0,scale=1.,n=1,jitter=False,valid=True):
            frame=np.full((220,360,3),160,np.uint8)
            for x in (110,220):cv2.circle(frame,(x+offset,104),7,(5,5,5),-1)
            tx=160*(1-scale)+dx;ty=110*(1-scale)+dy
            image=cv2.warpAffine(frame,np.float32([[scale,0,tx],[0,scale,ty]]),(360,220),
                                 flags=cv2.INTER_NEAREST,borderValue=(160,160,160))
            def box(x,y,w,h):return [round(x*scale+tx),round(y*scale+ty),round(w*scale),round(h*scale)]
            loc=Loc(Box(*box(50,40,230,150),1),Roi(*box(75,80,70,48),24,80),
                    Roi(*box(185,80,70,48),24,80),int(valid),1,2 if valid else 0)
            if jitter:
                loc.left.x-=4;loc.left.w+=8;loc.right.x+=3;loc.right.w-=6
            for _ in range(n):
                e.lib.pc_gaze_step(e.context,image.ctypes.data,image.strides[0],360,220,C.byref(loc),100,20)
            return e.state()
        observe(n=2);e.last_sample=time.monotonic();self.assertTrue(e.calibrate())
        observe(-16,n=25)
        s=observe(-16,dx=32,dy=14,n=12)
        self.assertEqual((s['cal_mask'],s['stage']),(1,2))
        observe(0,dx=32,dy=14,n=36);s=observe(16,dx=32,dy=14,n=36)
        self.assertEqual(s['cal_mask'],7)
        for dx,dy,scale in ((32,14,1.),(-28,-12,1.),(20,8,1.2),(-16,4,.85),(0,0,1.)):
            s=observe(0,dx=dx,dy=dy,scale=scale,n=6)
            self.assertEqual(s['cal_mask'],7);self.assertEqual(s['direction_name'],'CENTER')
            self.assertLessEqual(abs(s['left_nx']-128),6)
            self.assertLessEqual(abs(s['right_nx']-128),6)
        s=observe(0,jitter=True,n=3)
        self.assertEqual((s['lx'],s['lw'],s['rx'],s['rw']),(75,70,185,70))
        self.assertEqual(s['direction_name'],'CENTER')
        # Eye motion with unchanged model eye boxes still produces side gaze.
        self.assertEqual(observe(-16,n=14)['direction_name'],'LEFT')
        observe(0,n=10);s=observe(16,n=14)
        self.assertEqual((s['direction_name'],s['event_seq']),('RIGHT',2))
        s=observe(0,scale=1.5,n=3)
        self.assertFalse(s['valid']);self.assertEqual(s['cal_mask'],7)
        self.assertEqual(s['paused'],16)

    def test_manifest_rejects_drift(self):
        from pc_gaze import check_gaze_files
        from unittest.mock import mock_open
        manifest=json.loads((ROOT/'pc_runtime/gaze_manifest.json').read_text())
        manifest['fields']=['wrong']
        with patch('pathlib.Path.read_text',return_value=json.dumps(manifest)):
            with self.assertRaises(RuntimeError):check_gaze_files()

class Workers(unittest.TestCase):
    def test_stop_during_inference_and_release(self):
        entered=threading.Event();release=threading.Event()
        class Engine:
            last_sample=None
            def reset(self):pass
            def close(self):pass
            def process(self,frame,sampled):
                entered.set();release.wait(3)
                return {}  # Must be discarded before annotation/tracing.
        class Camera:
            released=False
            def isOpened(self):return True
            def set(self,*args):pass
            def read(self):return True,eye_frame()
            def release(self):self.released=True
        cap=Camera();worker=GazeWorker(Engine(),lambda index:cap)
        try:
            worker.request('camera',0);self.assertTrue(entered.wait(2))
            epoch=worker.request('stop');release.set()
            item=worker.results.get(timeout=3)
            self.assertEqual((item['epoch'],item['state']),(epoch,'stopped'))
            self.assertTrue(cap.released)
        finally:release.set();worker.close();worker.thread.join(3)

    def test_camera_read_failure_and_history_survive_coalescing(self):
        class Camera:
            released=False
            def isOpened(self):return True
            def set(self,*args):pass
            def read(self):return False,None
            def release(self):self.released=True
        cap=Camera();worker=GazeWorker(GazeEngine(),lambda index:cap)
        try:
            worker.request('camera',0);item=worker.results.get(timeout=3)
            self.assertEqual(item['state'],'error');self.assertTrue(cap.released)
            self.assertNotIn('frame',item)
            worker.record('event','LEFT event',direction='LEFT',event_seq=1)
            worker.publish(worker.epoch,state='notice',message='first')
            worker.publish(worker.epoch,state='notice',message='second')
            item=worker.results.get(timeout=2)
            self.assertEqual(item['message'],'second')
            self.assertTrue(any(e['kind']=='event' for e in item['history']))
        finally:worker.close();worker.thread.join(3)

class UI(unittest.TestCase):
    def test_targets_direction_watchdog_stop_and_export(self):
        import tkinter as tk
        class Worker:
            epoch=0
            def __init__(self):self.results=queue.Queue();self.commands=[]
            def request(self,*args):self.epoch+=1;self.commands.append(args)
            def close(self):pass
        engine=GazeEngine();worker=Worker();root=tk.Tk();root.withdraw()
        app=GazePreview(root,worker)
        try:
            calibrated(engine)
            root.deiconify();root.update()
            app.running=True
            initial_height=app.canvas.winfo_height()
            app.apply_result(dict(state='camera',frame=eye_frame(),raw=eye_frame(),result=result_for(engine),epoch=0))
            root.update()
            self.assertEqual(app.canvas.winfo_height(),initial_height)
            self.assertEqual(worker.commands,[])  # Diagnosis text is not a window resize.
            self.assertIsNotNone(app.gaze)
            app.running=False
            for stage in (1,2,3):
                item=dict(state='camera',frame=eye_frame(),result=result_for(engine,stage=stage),epoch=0)
                app.apply_result(item)
                self.assertTrue(app.canvas.find_withtag('target'))
                self.assertIn('校准',app.status.get())
                x0,y0,x1,y1=app.canvas.coords(app.canvas.find_withtag('target')[0])
                self.assertAlmostEqual((x0+x1)/2/app.canvas.winfo_width(),{1:.08,2:.5,3:.92}[stage])
                self.assertAlmostEqual((y0+y1)/2/app.canvas.winfo_height(),.18)
            app.apply_result(dict(state='camera',frame=eye_frame(),result=result_for(engine,stage=2,
                                  paused=2,cal_left_count=16,cal_right_count=5,settle_ms=2000),epoch=0))
            self.assertIn('单眼暂失',app.status.get())
            self.assertIn('16/16',app.progress_text.get());self.assertIn('5/16',app.progress_text.get())
            root.update()
            self.assertEqual(app.canvas.winfo_height(),initial_height)
            s=step(engine,20,100,n=14)
            item=dict(state='camera',frame=eye_frame(),result=result_for(engine),epoch=0)
            app.apply_result(item)
            self.assertIn('LEFT',app.status.get());self.assertFalse(app.canvas.find_withtag('target'))
            self.assertEqual(str(app.cells[1]['style']),'Selected.Direction.TLabel')
            app.running=True;app.last_sample=time.monotonic()-2
            app.poll()
            self.assertIsNone(app.current);self.assertIsNone(app.gaze)
            self.assertEqual(str(app.calibrate_button['state']),'disabled')
            app.apply_result(item);app.stop()
            self.assertIsNone(app.current)
            self.assertEqual(worker.commands[-1],('stop',))
            app.history=[dict(kind='event',direction='LEFT',text='test')]
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'日志.json'
                with patch('pc_gaze_preview.filedialog.asksaveasfilename',return_value=str(path)):app.export()
                data=json.loads(path.read_text(encoding='utf-8'))
                self.assertFalse(data['arm_timing']);self.assertEqual(data['records'][0]['direction'],'LEFT')
                raw=eye_frame();marked=raw.copy();marked[0,0]=255
                app.apply_result(dict(item,raw=raw,frame=marked))
                path=Path(temp)/'原图.png'
                with patch('pc_gaze_preview.filedialog.asksaveasfilename',return_value=str(path)):
                    app.save_diagnostic()
                from pc_model import cv2
                saved=cv2.imdecode(np.fromfile(path,np.uint8),1)
                self.assertTrue(np.array_equal(saved,raw))
                self.assertNotEqual(saved[0,0,0],marked[0,0,0])
                self.assertIn('gaze',json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))['result'])
        finally:app.close();engine.close()

if __name__=='__main__':unittest.main(verbosity=2)

"""PC integration tests; camera behavior uses a mock, never opens a device."""
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
from pc_model import Detector,annotate,cv2,fit_input,load_image,np
from pc_preview import Preview,PreviewWorker

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.detector=Detector()

    def test_input_and_abi(self):
        frame=np.zeros((240,320,3),np.uint8)
        result=self.detector.detect(frame)
        self.assertFalse(result['valid'])
        self.assertEqual(result['eye_count'],0)
        self.assertTrue(np.array_equal(annotate(frame,result),frame))
        for bad in (None,np.zeros((8,8,3),np.uint8),np.zeros((80,80),np.uint8),np.zeros((80,80,3),np.float32)):
            with self.assertRaises(ValueError):self.detector.detect(bad)
        self.assertEqual(fit_input(np.zeros((1080,1920,3),np.uint8)).shape,(720,1280,3))
        # Same memory shape with non-contiguous channel views is copied safely.
        self.assertFalse(self.detector.detect(frame[:,:,::-1])['valid'])

    def test_private_replay(self):
        manifest=ROOT.parent/'local/eye_captures/auto_replay/manifest.json'
        if not manifest.exists():self.skipTest('private replay inputs are not distributed')
        for sample in json.loads(manifest.read_text(encoding='utf-8')):
            frame=cv2.imdecode(np.fromfile(sample['path'],dtype=np.uint8),cv2.IMREAD_COLOR)
            if sample.get('crop'):
                x,y,w,h=sample['crop'];frame=frame[y:y+h,x:x+w].copy()
            unchanged=frame.copy()
            result=self.detector.detect(frame)
            self.assertEqual(result['valid'],bool(sample['expected']),sample['sample'])
            annotate(frame,result)
            self.assertTrue(np.array_equal(frame,unchanged))

    def test_late_result_is_discarded(self):
        entered=threading.Event();release=threading.Event()
        frame=np.zeros((100,100,3),np.uint8)
        class Slow:
            def detect(self,image):
                entered.set();release.wait(3)
                return dict(valid=False)
        with patch('pc_preview.load_image',return_value=frame):
            worker=PreviewWorker(Slow())
            try:
                worker.request('image','unused')
                self.assertTrue(entered.wait(2))
                stop_epoch=worker.request('stop')
                release.set()
                reply=worker.results.get(timeout=3)
                self.assertEqual((reply['epoch'],reply['state']),(stop_epoch,'stopped'))
            finally:release.set();worker.close();worker.thread.join(2)

    def test_camera_error_releases_device(self):
        class Camera:
            released=False
            def isOpened(self):return True
            def set(self,*args):return True
            def read(self):return False,None
            def release(self):self.released=True
        camera=Camera()
        worker=PreviewWorker(self.detector,lambda index:camera)
        try:
            worker.request('camera',0)
            reply=worker.results.get(timeout=3)
            self.assertEqual(reply['state'],'error')
            self.assertTrue(camera.released)
            self.assertNotIn('frame',reply)
        finally:worker.close();worker.thread.join(2)

    def test_unicode_path_and_bad_image(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'测试.png'
            ok,png=cv2.imencode('.png',np.zeros((80,100,3),np.uint8))
            self.assertTrue(ok);path.write_bytes(png.tobytes())
            self.assertEqual(load_image(path).shape,(80,100,3))
            path.write_bytes(b'not a picture')
            with self.assertRaises(ValueError):load_image(path)

    def test_tk_loading_and_stop(self):
        import tkinter as tk
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'blank.png'
            _,png=cv2.imencode('.png',np.zeros((80,100,3),np.uint8))
            path.write_bytes(png.tobytes())
            root=tk.Tk();root.withdraw()
            app=Preview(root,path)
            try:
                limit=time.monotonic()+5
                while app.current is None and time.monotonic()<limit:
                    root.update();time.sleep(.02)
                self.assertIsNotNone(app.current)
                self.assertIsNotNone(app.photo)
                self.assertIn('未找到可靠双眼对',app.status.get())
                self.assertEqual(app.current['state'],'image')
                app.stop()
                self.assertIsNone(app.current)
                self.assertEqual(str(app.save['state']),'disabled')
                self.assertFalse(app.canvas.find_all())
            finally:
                app.close();app.worker.thread.join(2)

if __name__=='__main__':unittest.main(verbosity=2)

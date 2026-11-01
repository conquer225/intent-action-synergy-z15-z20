import time,threading
import numpy as np
from vision_demo.session import Frame
import unittest
from vision_demo.worker import VisionWorker

class FailedCapture:
    generation=0
    def __init__(self):self.released=False
    def read(self,now):raise RuntimeError('capture interrupted')
    def close(self):raise RuntimeError('DMA still running')
    def release_after_reset(self):self.released=True

class OwnershipTests(unittest.TestCase):
    def test_failed_capture_retains_owner_until_verified_pl_reset(self):
        source=FailedCapture()
        worker=VisionWorker(lambda *args:source,object(),None)
        worker.select(dict(generation=0,source='ov5640',mode='original'))
        worker.thread.join(2)
        self.assertFalse(worker.thread.is_alive())
        with self.assertRaisesRegex(RuntimeError,'retain'):worker.close()
        self.assertFalse(source.released)
        self.assertIs(worker.source,source)
        worker.close(pl_reset=True)
        self.assertTrue(source.released)

class SequenceTests(unittest.TestCase):
    def test_repeated_and_backwards_frames_do_not_reach_processor(self):
        captured=time.monotonic()-.2;done=threading.Event();calls=[]
        frames=[Frame('ov5640',1,sequence,stamp,np.zeros((8,8,3),np.uint8)) for sequence,stamp in
                [(1,captured),(1,captured),(0,captured-.01),(2,captured+.01)]]
        class Source:
            generation=1
            def read(self,now):
                if frames:return frames.pop(0)
                done.set();return None
            def close(self):pass
        class Processor:
            backend='PL fixture';running=False
            def process(self,rgb,mode,reset):calls.append(reset);return rgb
        w=VisionWorker(lambda *args:Source(),Processor(),None)
        w.select(dict(source='ov5640',generation=1,mode='original'))
        self.assertTrue(done.wait(1));w.close()
        self.assertEqual(calls,[True,False])

class PupilPipelineTests(unittest.TestCase):
    def test_full_resolution_pupil_observation_does_not_run_discarded_pl_frame(self):
        done=threading.Event();image=np.zeros((480,640,3),np.uint8)
        frames=[Frame('tobii',1,1,time.monotonic()-.1,image)]
        class Source:
            generation=1
            def read(self,now):
                if frames:return frames.pop(0)
                done.set();return None
            def close(self):pass
        class Processor:
            backend='PL fixture';running=False
            def process(self,*args,**kwargs):raise AssertionError('Pupil source must keep full resolution')
        class Detector:
            def detect(self,rgb):return dict(valid=False,pupils=[])
        worker=VisionWorker(lambda *args:Source(),Processor(),Detector())
        worker.select(dict(source='tobii',generation=1,mode='pupil'))
        self.assertTrue(done.wait(2));result,error=worker.snapshot(time.monotonic());worker.close()
        self.assertIsNone(error);self.assertIsNotNone(result)
        self.assertEqual(result['rgb'].shape,(480,640,3))
        self.assertEqual(result['backend'],'PS OpenCV pupil / full source resolution')

if __name__=='__main__':unittest.main()

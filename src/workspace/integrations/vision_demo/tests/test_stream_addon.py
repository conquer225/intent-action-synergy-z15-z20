import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'ps_tobii/src'))
from vision_demo.addon import VisionAddon

class GPIO:
    value=3
    def read(self,address):return self.value
    def write(self,address,value):pass

class StreamSwitchTests(unittest.TestCase):
    def test_ov_modes_use_only_autonomous_video_and_tobii_switch_releases_it(self):
        events=[];gpio=GPIO()
        class Stream:
            active=False
            def start(self,mode):self.active=True;events.append(('stream',mode))
            def close(self,pl_reset=False):self.active=False;events.append(('stream_close',pl_reset))
            def service(self):pass
            def snapshot(self):return dict(processing_backend='PL pixel pipeline',ps_frame_submission=False)
        class Worker:
            def __init__(self,*args):events.append(('tobii_worker',None))
            def select(self,row):self.row=row
            def snapshot(self,now):return None,None
            def close(self,pl_reset=False):events.append(('worker_close',pl_reset))
        overlay=SimpleNamespace(ip_dict={'vision_keys_0':{'phys_addr':0x43c40000}},vision_keys_0=gpio,vision_core_0=object())
        with patch('vision_demo.addon.ContinuousVideo',return_value=Stream()),patch('vision_demo.addon.PupilDetector'),patch('vision_demo.addon.Presenter'),patch('vision_demo.addon.VisionWorker',Worker),patch('vision_demo.addon.PLProcessor') as old:
            from vision_demo.session import MODES
            addon=VisionAddon(overlay,dict(streaming=True,camera_library='native',enabled_image_modes=[m[0] for m in MODES]),lambda:None)
            def press(now):
                gpio.value=3;addon.poll_key(now);addon.poll_key(now+.07)
                gpio.value=2;addon.poll_key(now+.14)
                self.assertTrue(addon.poll_key(now+.21))
            press(0);self.assertEqual(events,[]) # Caller can stop controls before service starts DMA.
            addon.service(.22)
            for mode in range(1,9):press(mode);addon.service(mode+.22)
            self.assertFalse(old.called)
            self.assertEqual(events,[('stream',i) for i in range(9)])
            press(9);addon.service(9.22)
            self.assertFalse(addon.streaming);self.assertEqual(addon.snapshot(9.22)['source'],'tobii')
            self.assertEqual(events[-2:],[('stream_close',False),('tobii_worker',None)])
            press(10);addon.service(10.22)
            self.assertEqual(events[-2:],[('worker_close',False),('stream',0)])
            self.assertFalse(addon.snapshot(10.23)['ps_frame_submission']);addon.close()

class TobiiOwnerLifetimeTests(unittest.TestCase):
 def test_repeated_image_modes_reuse_one_usb_owner_and_exit_releases_it(self):
  owners=[]
  class Owner:
   def __init__(self,*args,**kwargs):self.generation=args[0];self.closed=False;owners.append(self)
   def read(self,now):return self.generation
   def close(self):self.closed=True
  overlay=SimpleNamespace(ip_dict={'vision_keys_0':{'phys_addr':0x43c40000}},vision_keys_0=GPIO(),vision_core_0=object())
  with patch('vision_demo.addon.ContinuousVideo'),patch('vision_demo.addon.PupilDetector'),patch('vision_demo.addon.Presenter'),patch('vision_demo.addon.TobiiImages',Owner):
   addon=VisionAddon(overlay,dict(streaming=True,camera_library='native',tobii_binary='worker'),lambda:None)
   first=addon.factory('tobii',1);self.assertEqual(first.read(0),1);first.close()
   second=addon.factory('tobii',2);self.assertEqual(second.read(1),2)
   self.assertEqual(len(owners),1);self.assertFalse(owners[0].closed)
   addon.leave();self.assertTrue(owners[0].closed)

class FourPageSwitchTests(unittest.TestCase):
 def test_camera_halts_before_signal_service_and_key0_stops_music_before_camera(self):
  from vision_demo.signal_core import SignalPages
  events=[];gpio=GPIO();gpio.value=3
  class Stream:
   active=False
   def start(self,mode):events.append('camera_start');self.active=True
   def close(self,pl_reset=False):events.append('camera_halt');self.active=False
   def service(self):pass
   def snapshot(self):return {}
  class Signal:
   def __init__(self,*a):self.pages=SignalPages()
   def next(self):return self.pages.next()
   def service(self,now):events.append('signal_'+('fatigue','emotion','music','audio')[self.pages.index])
   def leave(self):events.append('music_stop');self.pages.leave()
   def snapshot(self,now):return dict(page=('fatigue','emotion','music','audio')[self.pages.index])
   def close(self):events.append('signal_close')
  overlay=SimpleNamespace(ip_dict={'vision_keys_0':{'phys_addr':0x43c40000}},vision_keys_0=gpio,vision_core_0=object())
  with patch('vision_demo.addon.ContinuousVideo',return_value=Stream()),patch('vision_demo.addon.PupilDetector'),patch('vision_demo.addon.Presenter'),patch('vision_demo.signal_runtime.SignalRuntime',Signal):
   v=VisionAddon(overlay,dict(streaming=True,signal_pages=True,camera_library='native'),lambda:None)
   def press(value,t):
    gpio.value=3;v.poll_key(t);v.poll_key(t+.07);gpio.value=value;v.poll_key(t+.14);self.assertTrue(v.poll_key(t+.21));v.service(t+.22)
   press(2,0);self.assertTrue(v.streaming)
   for k in range(4):press(1,k+1);self.assertFalse(v.streaming)
   self.assertLess(events.index('camera_halt'),events.index('signal_fatigue'))
   press(2,6);self.assertEqual(events[-2:],['music_stop','camera_start']);v.close()

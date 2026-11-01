import tempfile,unittest,wave
from pathlib import Path
import numpy as np
from vision_demo.signal_audio import PlaybackAnalysis,PLAudioFFT
from types import SimpleNamespace
class PlaybackTests(unittest.TestCase):
 def test_follows_position_clears_old_frames_and_rejects_wrong_asset_format(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'music.wav';n=np.arange(48000);x=(12000*np.sin(2*np.pi*1500*n/48000)).astype('<i2')
   with wave.open(str(p),'wb') as w:w.setparams((2,2,48000,0,'NONE',''));w.writeframes(np.stack((x,x),axis=1).tobytes())
   a=PlaybackAnalysis();v=dict(phase='feeding',source=str(p),position_frames_estimate=24000,revision=1)
   r=a.update(v,0);self.assertEqual(r['position_seconds'],.5);self.assertEqual(r['peak_hz'],1500)
   self.assertIsNone(a.update(v,.51));self.assertIsNone(a.update(dict(v,phase='completed'),.6))
   self.assertEqual(a.waterfall,[]);a.close()
 def test_pl_driver_uses_exact_windows_and_sticks_failed_after_timeout(self):
  class IP:
   mmio=SimpleNamespace(array=np.zeros(16384,dtype=np.uint32))
   def read(self,a):return 4
   def write(self,a,v):pass
  overlay=SimpleNamespace(ip_dict={'audio_fft_0':dict(phys_addr=0x43c50000)},audio_fft_0=IP())
  clock=[0.];f=PLAudioFFT(overlay,now=lambda:clock[0],sleep=lambda s:clock.__setitem__(0,clock[0]+.02))
  with self.assertRaisesRegex(RuntimeError,'timeout'):f(np.zeros(1024))
  with self.assertRaisesRegex(RuntimeError,'reset'):f(np.zeros(1024))

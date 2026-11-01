import json,subprocess,tempfile,unittest,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
class FadePCMTests(unittest.TestCase):
 def test_real_c_renderer_fades_and_rejects_non_pcm_without_hardware(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);exe=root/'player.exe';wav=root/'source.wav';out=root/'samples.raw'
   r=subprocess.run(['C:/mingw64/mingw64/bin/gcc.exe','-std=c11','-O2',str(ROOT/'native/signal_pcm.c'),'-o',str(exe)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   with wave.open(str(wav),'wb') as w:w.setparams((2,2,48000,0,'NONE',''));w.writeframes(np.full((144000,2),10000,dtype='<i2').tobytes())
   r=subprocess.run([str(exe),'--render',str(wav),str(out),'--volume','50'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
   self.assertFalse(json.loads(r.stdout)['hardware_opened']);x=np.frombuffer(out.read_bytes(),dtype='<i2').reshape(-1,2)
   self.assertEqual(len(x),144000);self.assertEqual(x[0,0],0);self.assertEqual(x[72000,0],5000);self.assertLess(abs(x[-1,0]),2)
   r=subprocess.run([str(exe),'--play',str(wav)],capture_output=True,text=True);self.assertNotEqual(r.returncode,0)

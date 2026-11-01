import ctypes,subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
class AudioFFTTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();dll=Path(cls.temp.name)/'audiofft.dll'
  subprocess.run(['C:/mingw64/mingw64/bin/g++.exe','-O2','-shared',str(ROOT/'hls/audio_fft.cpp'),'-o',str(dll)],check=True,capture_output=True)
  cls.lib=ctypes.CDLL(str(dll));cls.fn=cls.lib.audio_fft
  cls.fn.argtypes=[ctypes.POINTER(ctypes.c_int32)]*3
 @classmethod
 def tearDownClass(cls):
  import _ctypes
  handle=cls.lib._handle;cls.fn=None;cls.lib=None
  _ctypes.FreeLibrary(handle);cls.temp.cleanup()
 def check_vector(self,x):
  x=np.asarray(x,dtype=np.int32);r=np.zeros(513,dtype=np.int32);i=r.copy()
  self.fn(*[a.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)) for a in (x,r,i)])
  expected=np.fft.rfft(x)/1024
  np.testing.assert_allclose(r+1j*i,expected,rtol=0,atol=12)
 def test_impulse_dc_nyquist_sine_and_stereo_cancellation_reference(self):
  n=np.arange(1024)
  for x in (np.zeros(1024),np.full(1024,10000),np.where(n%2,-12000,12000),np.where(n==0,32767,0),20000*np.sin(2*np.pi*32*n/1024)):
   with self.subTest():self.check_vector(x)
 def test_random_full_scale_and_two_tones(self):
  n=np.arange(1024);rng=np.random.default_rng(20261020)
  for x in (rng.integers(-32768,32768,1024),10000*np.sin(2*np.pi*9*n/1024)+16000*np.cos(2*np.pi*71*n/1024)):
   self.check_vector(x)

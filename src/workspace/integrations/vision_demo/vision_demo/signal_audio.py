"""One analysis worker observes the existing PCM owner; it never owns audio output."""
import copy,threading,time,wave
from pathlib import Path
import numpy as np
from .signal_core import analyze_audio

class PLAudioFFT:
 def __init__(self,overlay,now=time.monotonic,sleep=time.sleep):
  if overlay.ip_dict.get('audio_fft_0',{}).get('phys_addr')!=0x43c50000:raise RuntimeError('Audio FFT HWH mismatch')
  self.ip=overlay.audio_fft_0;self.now=now;self.sleep=sleep;self.failed=False
 def __call__(self,values):
  if self.failed:raise RuntimeError('Audio FFT timed out; reset required before reuse')
  if not self.ip.read(0)&4:raise RuntimeError('Audio FFT is not idle')
  q=np.clip(np.rint(np.asarray(values)*32767),-32768,32767).astype(np.int32)
  self.ip.mmio.array[0x1000//4:0x1000//4+1024]=q.view(np.uint32)
  self.ip.read(0);self.ip.write(0,1);deadline=self.now()+.05
  while not self.ip.read(0)&2:
   if self.now()>deadline:self.failed=True;raise RuntimeError('Audio FFT timeout')
   self.sleep(.0005)
  r=self.ip.mmio.array[0x2000//4:0x2000//4+513].copy().view(np.int32)
  i=self.ip.mmio.array[0x3000//4:0x3000//4+513].copy().view(np.int32)
  return (r.astype(float)+1j*i.astype(float))/32768.

class PlaybackAnalysis:
 def __init__(self,fft=None):
  self.fft=fft;self.wav=None;self.path=None;self.key=None;self.updated=-float('inf');self.result=None;self.waterfall=[]
 def update(self,view,now):
  if view.get('phase')!='feeding':self.result=None;self.waterfall=[];return None
  path=view.get('source');position=view.get('position_frames_estimate');revision=view.get('revision')
  if type(position) is not int or position<1024 or not path:self.result=None;return None
  key=(revision,str(path),position)
  if key==self.key:return self.snapshot(now)
  if self.key and key[:2]!=self.key[:2]:self.waterfall=[]
  self.key=key
  if str(path)!=self.path:
   self.close();self.wav=wave.open(str(path),'rb');self.path=str(path)
   if (self.wav.getframerate(),self.wav.getnchannels(),self.wav.getsampwidth(),self.wav.getcomptype())!=(48000,2,2,'NONE'):raise ValueError('Analysis expects original48kHz stereo PCM16')
  if position>self.wav.getnframes():raise ValueError('Playback position outside asset')
  self.wav.setpos(position-1024);data=self.wav.readframes(1024)
  if len(data)!=4096:raise ValueError('Incomplete PCM analysis window')
  x=np.frombuffer(data,dtype='<i2').reshape(1024,2).astype(float)/32768.
  row=analyze_audio(x,48000,self.fft);row.update(position_seconds=position/48000.,source=str(path),revision=revision)
  self.waterfall.append(row['spectrum_dbfs']);self.waterfall=self.waterfall[-100:]
  row['waterfall']=list(self.waterfall);self.result=row;self.updated=now
  return row
 def snapshot(self,now):return copy.deepcopy(self.result) if now-self.updated<=.5 else None
 def close(self):
  if self.wav:self.wav.close()
  self.wav=None;self.path=None

class AudioAnalysisWorker:
 def __init__(self,session,fft=None):
  self.session=session;self.engine=PlaybackAnalysis(fft);self.lock=threading.Lock();self.stop=threading.Event();self.error=None;self.result=None;self.updated=-float('inf')
  self.thread=threading.Thread(target=self._run,name='music-spectrum',daemon=True);self.thread.start()
 def _run(self):
  while not self.stop.is_set():
   start=time.monotonic()
   try:
    result=self.engine.update(self.session.snapshot(),start)
    with self.lock:self.result=copy.deepcopy(result);self.updated=start;self.error=None
   except Exception as e:
    self.engine.result=None;self.engine.waterfall=[]
    with self.lock:self.result=None;self.error=str(e)
   self.stop.wait(max(.01,.08-(time.monotonic()-start)))
 def snapshot(self,now):
  with self.lock:return (copy.deepcopy(self.result) if now-self.updated<=.5 else None),self.error
 def close(self):
  self.stop.set();self.thread.join(1)
  if self.thread.is_alive():raise RuntimeError('Audio analysis worker did not exit')
  self.engine.close()

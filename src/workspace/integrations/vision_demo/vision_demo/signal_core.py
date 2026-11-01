"""Signal presentation arithmetic and selection policy; no I/O or model execution."""
import math
import numpy as np
CAP=['F3','F4','C3','C4','T7','T8','O1','O2']
PAGES=('fatigue','emotion','music','audio')
EMOTIONS={'funny':'bright','calm':'steady','boring':'steady','horror':'calm'}

def empty_eeg(reason='等待脑电数据',origin='live'):
 return dict(ok=False,origin=origin,source_id='',seq=None,reason=str(reason),raw=[],samples=[],fatigue=None,emotion=None,processing={},quality=[],calibration=[0,15],position_seconds=0.)

def normalize_eeg(packet):
 origin=packet.get('origin','live')
 if origin not in ('live','replay'):return empty_eeg('未知来源')
 if packet.get('stale') is not False:return empty_eeg(packet.get('reason') or '数据已过期',origin)
 f=packet.get('status',{}).get('fatigue',{});t=packet.get('telemetry',{})
 if t.get('channels')!=CAP or f.get('channel_map')!=CAP:return empty_eeg('通道位置不匹配',origin)
 try:
  raw=np.asarray(t['raw_samples'],dtype=float);samples=np.asarray(t['samples'],dtype=float)
  if raw.ndim!=2 or raw.shape[1]!=8 or not 1<=len(raw)<=1500 or samples.shape!=raw.shape or not np.isfinite(raw).all() or not np.isfinite(samples).all():raise ValueError()
  seq=f.get('seq');index=t.get('sample_index',0)
  if type(seq) is not int or seq<0 or type(index) is not int or index<0:raise ValueError()
 except (ValueError,KeyError,TypeError):return empty_eeg('波形或序号无效',origin)
 fatigue=None;emotion=None;level=f.get('level');e=f.get('emotion') or {}
 if f.get('valid') is True and level in ('normal','mild','severe'):
  score=f.get('score')
  if type(score) in (int,float) and math.isfinite(score) and 0<=score<=1:fatigue=dict(level=level,score=score,inference_seq=str(((f.get('processing') or {}).get('fatigue') or {}).get('feature_window',seq)))
 if e.get('valid') is True and e.get('label') in EMOTIONS:emotion=dict(raw=e['label'],inference_seq=str(((f.get('processing') or {}).get('emotion') or {}).get('feature_window',seq)))
 return dict(ok=True,origin=origin,source_id=str(packet.get('source_id','cyton')),seq=seq,reason=str(f.get('state','')),
  raw=raw.tolist(),samples=samples.tolist(),fatigue=fatigue,emotion=emotion,processing=f.get('processing') or {},
  quality=(f.get('sqi') or {}).get('channels',[]),calibration=[f.get('calibration_current',0),f.get('calibration_total',15)],
  position_seconds=float(packet.get('position_seconds',index/float(t.get('sample_rate_hz',250)))),source_label=str(packet.get('source_label','Cyton 八通道')))

class SignalPages:
 def __init__(self,enabled_pages=PAGES):
  self.enabled_pages=tuple(enabled_pages)
  if not self.enabled_pages or len(set(self.enabled_pages))!=len(self.enabled_pages) or any(p not in PAGES for p in self.enabled_pages):raise ValueError('invalid enabled signal pages')
  self.index=-1;self.music_armed=False
 @property
 def current(self):return self.enabled_pages[self.index] if self.index>=0 else None
 def next(self):
  self.index=(self.index+1)%len(self.enabled_pages)
  if self.current=='music':self.music_armed=True
  return self.current
 def leave(self):self.index=-1;self.music_armed=False

class MusicPolicy:
 def __init__(self):
  self.armed=False;self.source=None;self.last_seq=-1;self.candidate=None;self.confirmations=0
  self.current=None;self.started=-math.inf;self.last_valid=-math.inf;self.confirm_key=None;self.reason='进入音乐联动页后启用';self.events=[]
 def arm(self):self.armed=True
 def reset(self):self.__init__()
 def update(self,frame,now):
  source=(frame.get('origin'),frame.get('source_id'))
  if frame.get('ok') and source!=self.source:
   self.source=source;self.last_seq=-1;self.candidate=None;self.confirmations=0;self.confirm_key=None
   if self.current:
    self.current=None;self.started=-math.inf;self.last_valid=-math.inf;self.reason='数据来源改变，等待重新确认';return 'stop'
  fatigue=frame.get('fatigue');emotion=frame.get('emotion');choice=None
  if frame.get('ok'):
   if fatigue and fatigue.get('level')=='severe':choice='calm';reason='严重疲劳优先，选择舒缓组'
   elif emotion and emotion.get('raw') in EMOTIONS:choice=EMOTIONS[emotion['raw']];reason='情绪分类 '+emotion['raw']+' 对应选曲'
  seq=frame.get('seq')
  if choice is not None and type(seq) is int:
   if seq>=self.last_seq:self.last_valid=now
   # Duplicate messages are observations, never a second inference confirmation.
   if seq>self.last_seq:
    self.last_seq=seq
    branch=fatigue if fatigue and fatigue.get('level')=='severe' else emotion
    confirmation=(choice,(branch or {}).get('inference_seq',seq))
    if confirmation==self.confirm_key:return None
    self.confirm_key=confirmation
    if choice!=self.candidate:self.candidate=choice;self.confirmations=1
    else:self.confirmations+=1
    self.reason=reason
  else:
   self.candidate=None;self.confirmations=0
  if now-self.last_valid>3 and self.current:
   self.current=None;self.started=-math.inf;self.candidate=None;self.confirmations=0;self.reason='脑电结果失效，淡出停止';self.events.append(dict(time=now,source_position_seconds=frame.get('position_seconds',0.),action='stop',reason=self.reason));self.events=self.events[-24:];return 'stop'
  if not self.armed:return None
  if self.candidate and self.confirmations>=2 and self.candidate!=self.current and now-self.started>=20:
   self.current=self.candidate;self.started=now
   self.events.append(dict(time=now,source_position_seconds=frame.get('position_seconds',0.),action=self.current,reason=self.reason));self.events=self.events[-24:];return self.current
  return None

def analyze_audio(stereo,rate,fft=None):
 x=np.asarray(stereo,dtype=np.float64)
 if x.shape!=(1024,2) or not np.isfinite(x).all() or rate!=48000 or np.max(np.abs(x))>1.001:raise ValueError('Expected1024 PCM-normalized stereo frames at48kHz')
 window=np.hanning(1024);coherent=window.sum();transforms=[]
 for channel in range(2):
  values=x[:,channel]*window
  transforms.append(np.fft.rfft(values)/1024 if fft is None else fft(values))
 z=np.stack(transforms);power=np.mean(np.abs(z)**2,axis=0)
 amplitude=np.sqrt(power)*(2*1024/coherent);amplitude[0]/=2;amplitude[-1]/=2
 db=20*np.log10(np.maximum(amplitude,1e-6));freq=np.fft.rfftfreq(1024,1/rate)
 total=float(power[1:].sum());bands=[float(power[(freq>=lo)&(freq<hi)].sum())/total if total>1e-15 else 0. for lo,hi in ((20,250),(250,4000),(4000,24001))]
 rms=np.sqrt(np.mean(x*x,axis=0));peak=None if total<1e-15 else float(freq[1+np.argmax(power[1:])])
 return dict(spectrum_dbfs=db.tolist(),frequencies=freq.tolist(),peak_hz=peak,bands=bands,
  rms_dbfs=(20*np.log10(np.maximum(rms,1e-6))).tolist(),peak_dbfs=(20*np.log10(np.maximum(np.max(np.abs(x),axis=0),1e-6))).tolist(),
  waveform=x[::4].tolist(),backend='PS NumPy reference' if fft is None else 'PL FFT1024',scope='播放前源PCM / 同一文件与播放位置')

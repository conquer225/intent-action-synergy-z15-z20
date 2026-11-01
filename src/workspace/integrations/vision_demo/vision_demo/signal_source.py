"""Read-only live or explicitly selected public replay; no acquisition/control writes."""
import bisect,copy,hashlib,json,time
from pathlib import Path
import numpy as np
from .signal_core import CAP
class PublicReplay:
 def __init__(self,folder):
  folder=Path(folder);self.metadata=json.loads((folder/'replay.json').read_text(encoding='utf-8'));m=self.metadata
  if m.get('format')!='guardianloop-public-replay-v1' or m.get('channels')!=CAP or m.get('control_enabled') is not False:raise ValueError('Replay identity mismatch')
  path=folder/'eeg_replay.npz'
  if hashlib.sha256(path.read_bytes()).hexdigest()!=m['data_sha256']:raise ValueError('Replay waveform changed')
  with np.load(path,allow_pickle=False) as z:self.raw=z['raw'];self.filtered=z['filtered']
  if self.raw.shape!=(15000,8) or self.filtered.shape!=self.raw.shape or not np.isfinite(self.raw).all() or not np.isfinite(self.filtered).all():raise ValueError('Replay shape invalid')
  self.ends=[x['sample_end'] for x in m['results']]
  if self.ends!=sorted(set(self.ends)):raise ValueError('Replay result timeline invalid')
 def snapshot(self,position):
  base=dict(origin='replay',source_id=self.metadata['source_id'],source_label=self.metadata['source_label'],position_seconds=position,control_enabled=False)
  if not 0<=position<180:return dict(base,stale=True,reason='历史回放结束',status={},telemetry={})
  absolute=120+position;sample=int(absolute*250);display=int(absolute*50)
  index=bisect.bisect_right(self.ends,sample)-1
  f=copy.deepcopy(self.metadata['results'][index]['fatigue']) if index>=0 else dict(seq=0,channel_map=CAP,state='calibrating')
  start=max(0,display-200)
  return dict(base,stale=False,status=dict(fatigue=f),telemetry=dict(channels=CAP,raw_samples=self.raw[start:display].tolist(),samples=self.filtered[start:display].tolist(),sample_index=sample,sample_rate_hz=250,display_rate_hz=50))
class SignalSource:
 def __init__(self,bridge,replay=None):self.bridge=bridge;self.replay=replay;self.mode='live';self.started=0.;self.generation=0
 def select(self,mode,now):
  if mode not in ('live','replay') or mode=='replay' and self.replay is None:raise ValueError('Unavailable signal source')
  if mode!=self.mode:self.mode=mode;self.started=now;self.generation+=1
 def restart_replay(self,now):
  if self.replay is None:raise ValueError('Replay is unavailable')
  self.mode='replay';self.started=now;self.generation+=1
 def snapshot(self,now):
  row=self.bridge.snapshot() if self.mode=='live' else self.replay.snapshot(now-self.started)
  if self.mode=='replay':row['source_id']=row.get('source_id','')+':%d'%self.generation
  return row
 def close(self):
  if self.bridge is not None:self.bridge.close()

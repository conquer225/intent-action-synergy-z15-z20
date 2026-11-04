"""Four-page runtime sharing original HDMI ownership and isolated music PCM child."""
import hashlib,json,time
from pathlib import Path
import numpy as np
from .signal_core import SignalPages,MusicPolicy,normalize_eeg,empty_eeg,PAGES
from .signal_source import PublicReplay,SignalSource
from .signal_audio import AudioAnalysisWorker,PLAudioFFT
from .signal_render import SignalPresenter
class MusicLink:
 def __init__(self,session,tracks,volume=35):self.session=session;self.tracks=tracks;self.volume=volume;self.policy=MusicPolicy();self.track=None
 def arm(self):self.policy.arm()
 def update(self,frame,now):
  action=self.policy.update(frame,now)
  if action=='stop':self.session.stop();self.track=None
  elif action:
   if action not in self.tracks:raise ValueError('Music group missing')
   self.track=self.tracks[action];self.session.play(self.track['path'],volume=self.volume)
  return self.snapshot()
 def snapshot(self):
  return dict(reason=self.policy.reason,confirmations=min(self.policy.confirmations,2),genre=self.policy.current,
   title=(self.track or {}).get('title','尚未选曲'),events=list(self.policy.events),player=self.session.snapshot(),audible_verified=False)
 def close(self):
  self.policy.reset();self.track=None
  if not getattr(self.session,'closed',False):self.session.stop()

class SignalRuntime:
 def __init__(self,overlay,config):
  from eeg_demo_bridge import DemoBridge
  folder=Path(__file__).resolve().parent
  self.pages=SignalPages(config.get('enabled_signal_pages',PAGES))
  self.output_ready=False;self.active=False;self.frame=empty_eeg();self.presenter=SignalPresenter(config.get('font'),enabled_pages=self.pages.enabled_pages)
  # Live EEG uses the existing acquisition service; recordings load only on request.
  self.replay_folder=folder/'replay';self.selection=folder/'source_selection.json'
  self.token=self._read_selection().get('request_id');self.last_poll=-float('inf');self.cached_audio=None;self.error=None
  self.source=SignalSource(None)
  self.session=self.analysis=self.music=None
  if not set(self.pages.enabled_pages)&{'music','audio'}:
   self.source.bridge=DemoBridge();return
  from audio_session import PcmSession
  catalog=json.loads((folder/'music/catalog.json').read_text(encoding='utf-8'));tracks={}
  for key,row in catalog['tracks'].items():
   path=(folder/'music'/row['path']).resolve();path.relative_to(folder/'music')
   if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Music asset checksum')
   tracks[key]=dict(row,path=str(path))
  fft=PLAudioFFT(overlay)
  try:
   self.session=PcmSession([str(folder/'bin/signal-pcm')])
   try:self.analysis=AudioAnalysisWorker(self.session,fft)
   except Exception:self.session.close();raise
  except Exception:self.source.close();raise
  self.music=MusicLink(self.session,tracks)
  try:self.source.bridge=DemoBridge()
  except Exception:
   self.analysis.close();self.session.close();raise
 def _read_selection(self):
  try:
   if self.selection.stat().st_size>2048:raise ValueError('Source request too large')
   row=json.loads(self.selection.read_text(encoding='utf-8'))
   if row.get('mode') not in ('live','replay') or not isinstance(row.get('request_id'),str):raise ValueError('Invalid source request')
   return row
  except FileNotFoundError:return {}
 def next(self):
  self.active=True;page=self.pages.next()
  if self.pages.music_armed and self.music:self.music.arm()
  return page
 def service(self,now):
  if not self.active:return
  if now-self.last_poll>=.04:
   try:
    row=self._read_selection()
    if row and row['request_id']!=self.token:
     if row['mode']=='replay':
      if self.source.replay is None:self.source.replay=PublicReplay(self.replay_folder)
      self.source.restart_replay(now)
     else:self.source.select('live',now)
     self.token=row['request_id']
    self.error=None
   except (ValueError,OSError) as exc:self.error=str(exc)
   self.frame=normalize_eeg(self.source.snapshot(now));
   if self.output_ready and self.music:self.music.update(self.frame,now)
   self.last_poll=now
  self.cached_audio,analysis_error=self.analysis.snapshot(now) if self.analysis else (None,None)
  if analysis_error:self.error=analysis_error
 def _music_snapshot(self):
  return self.music.snapshot() if self.music else dict(reason='本次仅接入脑电分析',genre=None,title='',events=[],player=dict(phase='disabled'))
 def snapshot(self,now):
  m=self._music_snapshot();m['analysis_error']=self.error
  return dict(active=self.active,page=self.pages.current if self.active else None,source=self.frame.get('origin'),
   position_seconds=self.frame.get('position_seconds'),eeg_valid=self.frame.get('ok'),music=m,
   audio_analysis_backend=(self.cached_audio or {}).get('backend'),control_enabled=False)
 def compose(self,buffer,now):
  m=self._music_snapshot();m['analysis_error']=self.error
  rgb=self.presenter.render(self.pages.current,self.frame,m,self.cached_audio,now)
  np.copyto(buffer,rgb[...,::-1]);buffer.flush()
 def leave(self):
  if self.music:self.music.close()
  self.pages.leave();self.active=False;self.source.select('live',time.monotonic());self.frame=empty_eeg();self.cached_audio=None
  self.presenter.history=[];self.presenter.last_key=None
 def close(self):
  self.leave()
  if self.analysis:self.analysis.close()
  if self.session:self.session.close()
  self.source.close()

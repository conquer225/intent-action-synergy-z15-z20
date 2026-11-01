"""Loopback-only four-page preview; manually selected public replay, browser PCM audio."""
import argparse,io,json,threading,time,re,hashlib
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from PIL import Image
from vision_demo.signal_source import PublicReplay
from vision_demo.signal_core import normalize_eeg,empty_eeg,MusicPolicy,PAGES
from vision_demo.signal_audio import PlaybackAnalysis
from vision_demo.signal_render import SignalPresenter
HERE=Path(__file__).resolve().parent
class PreviewState:
 def __init__(self,assets,enabled_pages=PAGES):
  self.enabled_pages=tuple(enabled_pages)
  self.assets=assets;self.replay=PublicReplay(assets/'replay');self.presenter=SignalPresenter(enabled_pages=self.enabled_pages);self.policy=MusicPolicy();self.analysis=PlaybackAnalysis()
  self.tracks=json.loads((assets/'music/catalog.json').read_text(encoding='utf-8'))['tracks'];self.started=None;self.lock=threading.Lock();self.audio_revision=0;self.current=None;self.restart=None;self.paused_at=None
 def view(self,q):
  page=q.get('page',['fatigue'])[0]
  if page not in self.enabled_pages:raise ValueError('Page disabled for this release')
  now=time.monotonic();restart=q.get('restart',['0'])[0]
  if self.started is None or restart!=self.restart:
   self.started=now;self.restart=restart;self.paused_at=None;self.current=None;self.policy.reset();self.presenter.history=[]
  paused=q.get('paused',['0'])[0]=='1'
  if paused and self.paused_at is None:
   self.paused_at=now;armed=self.policy.armed;self.policy.reset();self.current=None
   if armed:self.policy.arm()
  if not paused and self.paused_at is not None:self.started+=now-self.paused_at;self.paused_at=None
  position_time=(self.paused_at if paused else now)-self.started
  frame=normalize_eeg(self.replay.snapshot(position_time))
  if page=='music' and not paused:self.policy.arm()
  action=self.policy.update(frame,now) if not paused else None
  if action=='stop':self.current=None
  elif action:self.current=action;self.audio_revision+=1
  position=max(0,min(48.,float(q.get('audio_position',['0'])[0])))
  actual=q.get('playing',['0'])[0]=='1' and q.get('audio_track',[''])[0]==self.current
  track=self.tracks.get(self.current,{})
  view=dict(phase='feeding' if actual else 'stopped',revision=self.audio_revision,
    source=str(self.assets/'music'/track.get('path','none')),position_frames_estimate=int(position*48000))
  a=self.analysis.update(view,now) if actual else None
  m=dict(reason=self.policy.reason,genre=self.current,title=track.get('title','尚未选曲'),confirmations=min(2,self.policy.confirmations),events=self.policy.events,player=view)
  image=self.presenter.render(page,frame,m,a,now)
  return image,dict(genre=self.current,title=m['title'],origin=frame['origin'],page=page,ended=position_time>=180,backend='PS NumPy reference',position_seconds=frame['position_seconds'])
class PreviewSessions:
 def __init__(self,assets):self.assets=assets;self.states=OrderedDict();self.lock=threading.Lock()
 def get(self,token):
  if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{32}',token):raise ValueError('Invalid preview session')
  with self.lock:
   if token in self.states:self.states.move_to_end(token);return self.states[token]
   if len(self.states)>=8:
    _,old=self.states.popitem(last=False);old.analysis.close()
   state=PreviewState(self.assets);self.states[token]=state;return state

class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  try:
   u=urlsplit(self.path);q=parse_qs(u.query)
   if u.path=='/':body=(HERE/'signal_brain_preview.html').read_bytes();kind='text/html; charset=utf-8'
   elif u.path in ('/eeg-demo','/console','/player','/upload') or u.path in ('/presentation.css','/eeg_demo.css','/eeg_demo.js','/eeg_demo_core.js','/eeg_recording.json','/system_mobile.js'):
    root=HERE.parent/'eeg_demo/runtime'
    names={'/eeg-demo':'eeg_demo.html','/console':'system_mobile.html','/player':'player.html','/upload':'upload.html'}
    name=names.get(u.path,u.path.lstrip('/'));local=HERE/name
    body=(local if name=='presentation.css' and local.is_file() else root/name).read_bytes()
    kind='text/css' if name.endswith('.css') else 'application/json' if name.endswith('.json') else 'text/javascript' if name.endswith('.js') else 'text/html; charset=utf-8'
   elif u.path=='/api/player':
    self.send_response(503);body=json.dumps({'error':'控制服务未启动，请在板端控制台操作'},ensure_ascii=False).encode('utf-8');self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
   elif u.path=='/gallery':body=(HERE/'report/presentation/gallery.html').read_bytes();kind='text/html; charset=utf-8'
   elif u.path.startswith('/hdmi/') and u.path.rsplit('/',1)[-1] in ('home.png','equipment.png','hand.png','pendulum_menu.png','pendulum_balance.png','pendulum_turn.png','speed.png','music.png','video_nav.png','speech.png','eye_positioning.png'):
    body=(HERE/'report/presentation/hdmi'/u.path.rsplit('/',1)[-1]).read_bytes();kind='image/png'
   elif u.path=='/frame':
    state=self.server.sessions.get(q.get('session',[''])[0])
    with state.lock:
     image,meta=state.view(q);out=io.BytesIO();Image.fromarray(image).save(out,format='PNG');body=out.getvalue()
    kind='image/png';self.send_response(200);self.send_header('X-Signal-State',json.dumps(meta,ensure_ascii=True));self.send_header('Access-Control-Expose-Headers','X-Signal-State');self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
   elif u.path in ('/music/calm.wav','/music/steady.wav','/music/bright.wav'):
    name=u.path.rsplit('/',1)[-1];catalog=json.loads((self.server.assets/'music/catalog.json').read_text(encoding='utf-8'))
    body=(self.server.assets/'music'/name).read_bytes()
    if hashlib.sha256(body).hexdigest()!=catalog['tracks'][name[:-4]]['sha256']:raise ValueError('Music checksum mismatch')
    kind='audio/wav'
   else:self.send_error(404);return
   self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
  except (ValueError,OSError,KeyError) as e:self.send_error(400,str(e))
 def log_message(self,*a):pass
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,default=HERE/'build/signal_assets');p.add_argument('--port',type=int,default=9130);a=p.parse_args()
 server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);server.assets=a.assets.resolve();server.sessions=PreviewSessions(server.assets)
 print('Four-page preview: http://127.0.0.1:%d (bundled EEG recording; no board control)'%a.port,flush=True);server.serve_forever()

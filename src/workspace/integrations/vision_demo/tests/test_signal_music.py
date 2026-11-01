import unittest
from vision_demo.signal_runtime import MusicLink
class Session:
 def __init__(self):self.calls=[];self.view=dict(phase='stopped',revision=0)
 def play(self,path,**kw):self.calls.append(('play',path));self.view.update(phase='starting',revision=len(self.calls))
 def stop(self):self.calls.append(('stop',None));self.view.update(phase='stopped')
 def snapshot(self):return self.view.copy()
 def close(self):self.stop()
class MusicLinkTests(unittest.TestCase):
 def test_only_confirmed_selection_plays_eof_waits_and_close_revokes(self):
  s=Session();m=MusicLink(s,{'bright':dict(path='bright.wav',title='Bright')})
  f=lambda seq:dict(ok=True,origin='live',source_id='test',seq=seq,emotion=dict(raw='funny'),fatigue=None)
  m.update(f(1),0);self.assertEqual(s.calls,[]);m.arm();m.update(f(1),1);m.update(f(2),2)
  self.assertEqual(s.calls,[('play','bright.wav')]);s.view['phase']='completed'
  m.update(f(3),3);self.assertEqual(len(s.calls),1)
  m.update(dict(ok=False),7);self.assertEqual(s.calls[-1][0],'stop')
  m.close();self.assertFalse(m.policy.armed)

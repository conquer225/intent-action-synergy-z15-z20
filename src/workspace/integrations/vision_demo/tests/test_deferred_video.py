"""Execute emitted cache-admission/frame-read code without board I/O.

The fixture isolates those statements from main's hardware setup and display
submission. It preserves Python local-variable semantics and uses real emitted
control flow, so prior non-video presentations can expose an unbound cursor.
"""
import ast,copy,os,sys,unittest
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


class DeferredVideoTests(unittest.TestCase):
 def test_first_cached_video_frame_is_available_after_signal_presentations(self):
  emitted=os.environ.get('GL_MEDIA_PLAYER_UNDER_TEST')
  if emitted:
   text=Path(emitted).read_text(encoding='utf-8')
  else:
   from patch_media import patch
   text=patch((ROOT.parent/'eeg_demo/runtime/media_player.py').read_text(encoding='utf-8'))
  program=ast.parse(text)
  main=next(n for n in program.body if isinstance(n,ast.FunctionDef) and n.name=='main')
  body=next(n.body for n in main.body if isinstance(n,ast.Try))
  def assigns(node,name):
   return isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)
  start=next(i for i,n in enumerate(body) if assigns(n,'source'))
  end=next(i for i,n in enumerate(body[start:],start) if assigns(n,'expander'))
  loop=next(n for n in body if isinstance(n,ast.While))
  at=next(i for i,n in enumerate(loop.body) if isinstance(n,ast.If) and isinstance(n.test,ast.Compare)
          and isinstance(n.test.left,ast.Name) and n.test.left.id=='block')
  until=next(i for i,n in enumerate(loop.body[at:],at) if assigns(n,'frame'))
  harness=ast.parse('def first_frame(BoundedChunks,state,live,unified,presented):\n while True:\n  pass\n')
  fn=harness.body[0];fn.body=copy.deepcopy(body[start:end])+fn.body
  fn.body[-1].body=copy.deepcopy(loop.body[at:until+1])+[ast.Return(value=ast.Name(id='frame',ctx=ast.Load()))]
  ast.fix_missing_locations(harness);namespace={};exec(compile(harness,'emitted-video-path','exec'),namespace)
  source=SimpleNamespace(meta=dict(width=288,height=512,format='gl-bgr24-lz4-v1'),
                         acquire=lambda **kw:(0,2),slots=[['frame-0','frame-1']])
  for prior_frames in (0,37):
   with self.subTest(prior_presentations=prior_frames):
    self.assertEqual(namespace['first_frame'](lambda *a,**kw:source,{'cache':'fixture'},True,SimpleNamespace(),prior_frames),'frame-0')

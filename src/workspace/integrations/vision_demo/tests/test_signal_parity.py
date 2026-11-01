"""Actual public replay compares original vector snapshots with independent deque path."""
import importlib.util,json,tempfile,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
class ReplayParityTests(unittest.TestCase):
 def test_original_models_produce_identical_outputs_with_reference_window_snapshot(self):
  source=ROOT.parents[1]/'local/signal_materials/lemon'
  if not source.is_dir():self.skipTest('Public raw preparation source available in maintained workspace only')
  sys.path.insert(0,str(ROOT.parent/'eeg_demo/brain_runtime'))
  import prepare_signal_replay as replay
  old=replay.primary_windows
  def reference(raw,filtered,scale):
   counts=np.stack(list(raw)).astype(float);uv=(counts-counts.mean(axis=0))*scale
   values=np.stack(list(filtered));return counts,uv,values-values.mean(axis=0)
  try:
   with tempfile.TemporaryDirectory() as folder:
    replay.primary_windows=reference;replay.prepare(source,Path(folder),ROOT.parent/'eeg_demo/brain_runtime')
    fresh=json.loads((Path(folder)/'replay.json').read_text(encoding='utf-8'))
    delivered=json.loads((ROOT/'build/signal_assets/replay/replay.json').read_text(encoding='utf-8'))
    errors=[]
    def compare(a,b,path='results'):
     if isinstance(a,float) and isinstance(b,(float,int)):
      errors.append(abs(a-b));self.assertAlmostEqual(a,b,delta=1e-10,msg=path)
     elif isinstance(a,dict):
      self.assertEqual(set(a),set(b),path)
      for key in a:compare(a[key],b[key],path+'.'+key)
     elif isinstance(a,list):
      self.assertEqual(len(a),len(b),path)
      for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+'[%d]'%i)
     else:self.assertEqual(a,b,path)
    compare(fresh['results'],delivered['results'])
    print('PUBLIC_REPLAY_PARITY windows=%d max_numeric_delta=%g labels/validity exact'%(len(fresh['results']),max(errors)))
    self.assertEqual(fresh['model_hashes'],delivered['model_hashes'])
  finally:replay.primary_windows=old

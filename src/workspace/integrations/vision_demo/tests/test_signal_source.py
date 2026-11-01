import tempfile,unittest,json
from pathlib import Path
import numpy as np
from vision_demo.signal_source import PublicReplay,SignalSource
from vision_demo.signal_core import CAP
class ReplayTests(unittest.TestCase):
 def test_replay_never_starts_automatically_and_switch_preserves_manual_time(self):
  class Bridge:
   def snapshot(self):return dict(origin='live',stale=True,reason='not connected')
   def close(self):pass
  class Replay:
   def snapshot(self,t):return dict(origin='replay',position_seconds=t)
  s=SignalSource(Bridge(),Replay());self.assertEqual(s.snapshot(20)['origin'],'live')
  s.select('replay',20);self.assertEqual(s.snapshot(25)['position_seconds'],5)
  s.select('replay',26);self.assertEqual(s.snapshot(27)['position_seconds'],7)
  s.select('live',28);self.assertEqual(s.snapshot(29)['origin'],'live')
 def test_real_pack_uses_same_clock_and_end_clears_results(self):
  p=Path(__file__).resolve().parents[1]/'build/signal_assets/replay'
  if not p.exists():self.skipTest('Generated public replay artifact not present')
  r=PublicReplay(p);a=r.snapshot(0);b=r.snapshot(10)
  self.assertEqual(a['origin'],'replay');self.assertEqual(a['telemetry']['channels'],CAP)
  self.assertEqual(b['position_seconds'],10);self.assertGreater(b['telemetry']['sample_index'],a['telemetry']['sample_index'])
  self.assertTrue(r.snapshot(180)['stale']);self.assertEqual(r.snapshot(180)['status'],{})

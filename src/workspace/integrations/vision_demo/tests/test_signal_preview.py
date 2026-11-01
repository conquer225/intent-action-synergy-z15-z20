import unittest
from unittest.mock import patch
from types import SimpleNamespace
import preview_signals
class PreviewIsolationTests(unittest.TestCase):
 def test_browser_sessions_have_independent_sources_and_bounded_state(self):
  with patch.object(preview_signals,'PreviewState',side_effect=lambda assets:SimpleNamespace(analysis=SimpleNamespace(close=lambda:None))):
   pool=preview_signals.PreviewSessions(None)
   first=pool.get('a'*32);second=pool.get('b'*32)
   self.assertIsNot(first,second);self.assertIs(first,pool.get('a'*32))
   for key in range(20):pool.get('%032x'%key)
   self.assertLessEqual(len(pool.states),8)
   with self.assertRaises(ValueError):pool.get('../../other')

 def test_default_page_uses_real_recording_without_live_device_entry(self):
  from pathlib import Path
  assets=Path(__file__).resolve().parents[1]/'build/signal_assets'
  state=preview_signals.PreviewState(assets)
  image,meta=state.view({'page':['fatigue']})
  self.assertEqual(meta['origin'],'replay')
  self.assertEqual(image.shape,(720,1280,3))

 def test_default_preview_restores_music_and_audio_views(self):
  from pathlib import Path
  assets=Path(__file__).resolve().parents[1]/'build/signal_assets'
  state=preview_signals.PreviewState(assets)
  self.assertEqual(state.enabled_pages,('fatigue','emotion','music','audio'))
  for page in ('music','audio'):
   image,meta=state.view({'page':[page]})
   self.assertEqual(image.shape,(720,1280,3));self.assertEqual(meta['page'],page)

 def test_pause_freezes_recording_time_and_restart_clears_old_selection(self):
  from pathlib import Path
  assets=Path(__file__).resolve().parents[1]/'build/signal_assets'
  state=preview_signals.PreviewState(assets)
  with patch.object(preview_signals.time,'monotonic',return_value=100):state.view({})
  with patch.object(preview_signals.time,'monotonic',return_value=105):_,paused=state.view({'paused':['1']})
  with patch.object(preview_signals.time,'monotonic',return_value=135):_,held=state.view({'paused':['1']})
  self.assertEqual(paused['position_seconds'],held['position_seconds']);self.assertIsNone(held['genre'])
  with patch.object(preview_signals.time,'monotonic',return_value=140):_,resumed=state.view({})
  self.assertEqual(resumed['position_seconds'],5)
  with patch.object(preview_signals.time,'monotonic',return_value=142):_,fresh=state.view({'restart':['1']})
  self.assertEqual(fresh['position_seconds'],0);self.assertIsNone(fresh['genre'])

 def test_pause_keeps_music_visit_for_resume_on_another_page(self):
  from pathlib import Path
  state=preview_signals.PreviewState(Path(__file__).resolve().parents[1]/'build/signal_assets')
  state.enabled_pages=('fatigue','emotion','music','audio')
  state.presenter.enabled_pages=state.enabled_pages
  with patch.object(preview_signals.time,'monotonic',return_value=100):state.view({'page':['music']})
  self.assertTrue(state.policy.armed)
  with patch.object(preview_signals.time,'monotonic',return_value=101):state.view({'page':['audio'],'paused':['1']})
  self.assertTrue(state.policy.armed);self.assertIsNone(state.current)
  with patch.object(preview_signals.time,'monotonic',return_value=120):state.view({'page':['audio']})
  self.assertTrue(state.policy.armed)

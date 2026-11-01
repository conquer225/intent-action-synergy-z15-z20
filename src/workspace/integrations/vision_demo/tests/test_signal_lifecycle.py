import tempfile,unittest,sys,types
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from vision_demo.signal_runtime import SignalRuntime
class LifecycleTests(unittest.TestCase):
 def test_default_recording_page_switch_never_restarts_source_and_old_audio_blocks_music(self):
  class Bridge:
   def snapshot(self):return dict(stale=True,reason='not connected')
   def close(self):pass
  class Session:
   closed=False
   def __init__(self,*a):self.calls=[]
   def snapshot(self):return dict(phase='stopped',revision=0)
   def stop(self):self.calls.append('stop')
   def close(self):self.closed=True
  class Analysis:
   thread=SimpleNamespace(is_alive=lambda:False)
   def __init__(self,*a):pass
   def snapshot(self,now):return None,None
   def close(self):pass
  module=types.ModuleType('eeg_demo_bridge');module.DemoBridge=Bridge
  audio=types.ModuleType('audio_session');audio.PcmSession=Session
  # Runtime assets live next to installed module; use actual package asset content through Path redirection.
  assets=Path(__file__).resolve().parents[1]/'build/signal_assets'
  if not assets.exists():self.skipTest('Prepared assets unavailable')
  import vision_demo.signal_runtime as runtime
  class Folder:
   def resolve(self):return self
   @property
   def parent(self):return assets
  original=runtime.Path
  def path(value):return Folder() if str(value).endswith('signal_runtime.py') else original(value)
  with patch.dict(sys.modules,eeg_demo_bridge=module,audio_session=audio),patch.object(runtime,'Path',side_effect=path),patch.object(runtime,'PLAudioFFT',return_value=None),patch.object(runtime,'AudioAnalysisWorker',Analysis):
   s=SignalRuntime(None,{})
   with patch.object(s.music,'update',wraps=s.music.update) as update:
    self.assertEqual([s.next() for _ in range(4)],['fatigue','emotion','music','audio'])
    s.service(100);self.assertFalse(update.called)
    s.service(100.05);self.assertAlmostEqual(s.frame['position_seconds'],.05,places=6)
    self.assertFalse(update.called);s.output_ready=True;s.service(101);self.assertEqual(update.call_count,1)
   self.assertEqual(s.source.mode,'replay');s.leave();self.assertFalse(s.pages.music_armed);s.close()

 def test_invalid_fft_never_starts_bridge_or_pcm_threads(self):
  import vision_demo.signal_runtime as runtime
  from unittest.mock import Mock
  assets=Path(__file__).resolve().parents[1]/'build/signal_assets'
  if not assets.exists():self.skipTest('Prepared assets unavailable')
  class Folder:
   def resolve(self):return self
   @property
   def parent(self):return assets
  original=runtime.Path
  def path(value):return Folder() if str(value).endswith('signal_runtime.py') else original(value)
  bridge=Mock();session=Mock()
  eeg=types.ModuleType('eeg_demo_bridge');eeg.DemoBridge=bridge
  audio=types.ModuleType('audio_session');audio.PcmSession=session
  with patch.dict(sys.modules,eeg_demo_bridge=eeg,audio_session=audio),patch.object(runtime,'Path',side_effect=path),patch.object(runtime,'PLAudioFFT',side_effect=ValueError('FFT identity invalid')):
   with self.assertRaisesRegex(ValueError,'FFT identity invalid'):SignalRuntime(None,{'enabled_signal_pages':('fatigue','emotion','music','audio')})
  bridge.assert_not_called();session.assert_not_called()

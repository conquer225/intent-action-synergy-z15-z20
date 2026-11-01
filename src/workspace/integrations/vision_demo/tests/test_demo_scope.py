import unittest
from unittest.mock import patch

from vision_demo.session import VisionSession
from vision_demo.signal_core import SignalPages


class DemoScopeTests(unittest.TestCase):
    def test_selected_modes_cycle_original_hardware_indices(self):
        session = VisionSession(enabled_modes=('neon', 'trails', 'motion'))
        self.assertEqual(session.snapshot()['index'], 1)
        self.assertEqual([session.snapshot()['mode']] +
                         [session.next_mode()['mode'] for _ in range(3)],
                         ['neon', 'trails', 'motion', 'neon'])
        self.assertEqual(session.snapshot()['index'], 1)
        self.assertEqual(session.source, 'ov5640')

    def test_two_signal_pages_cannot_arm_music(self):
        pages = SignalPages(enabled_pages=('fatigue', 'emotion'))
        self.assertEqual([pages.next() for _ in range(6)], ['fatigue', 'emotion'] * 3)
        self.assertFalse(pages.music_armed)

    def test_brain_only_runtime_never_constructs_audio_resources(self):
        from vision_demo.signal_runtime import SignalRuntime
        with patch('vision_demo.signal_runtime.PublicReplay'), \
             patch('vision_demo.signal_runtime.SignalSource'), \
             patch('vision_demo.signal_runtime.SignalPresenter'), \
             patch('vision_demo.signal_runtime.PLAudioFFT', side_effect=AssertionError('FFT created')), \
             patch('vision_demo.signal_runtime.AudioAnalysisWorker', side_effect=AssertionError('worker created')):
            runtime = SignalRuntime(None, {'enabled_signal_pages': ['fatigue', 'emotion']})
            self.assertEqual([runtime.next() for _ in range(4)], ['fatigue', 'emotion'] * 2)
            self.assertIsNone(runtime.snapshot(0)['audio_analysis_backend'])
            runtime.close()

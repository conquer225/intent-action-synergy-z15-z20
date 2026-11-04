"""NPU EEG pages consume received results without substituting bundled features."""
from pathlib import Path
import json
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/workspace/integrations/z20_compute'))
from z20_compute.visual_pipeline import VisualPipeline


class LiveNPUEntryTests(unittest.TestCase):
    def run_page(self, result, index=0, *, audio_assets=True):
        with tempfile.TemporaryDirectory() as temporary:
            stopped, rows = threading.Event(), []
            sound = Path(temporary) / 'sound'
            if audio_assets:
                sound.mkdir()
                (sound / 'manifest.json').write_text(json.dumps(dict(
                    windows=[dict(class_id=index) for index in range(3)])), encoding='utf-8')

            def publish(mode, value, *, epoch):
                rows.append((mode, value, epoch))
                stopped.set()

            submit = Mock(side_effect=AssertionError('EEG page must use received features'))
            visual = VisualPipeline.__new__(VisualPipeline)
            visual.pipeline = SimpleNamespace(sound_root=sound,
                stopped=stopped, runtime=SimpleNamespace(status=lambda: result, submit_local=submit))
            visual.state = SimpleNamespace(snapshot=lambda: dict(
                menu=False, mode='npu', sample_index=index, epoch=7), publish=publish)
            visual.audio_loop()
            submit.assert_not_called()
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0][0], rows[0][2]), ('npu', 7))
            return rows[0][1]

    def test_received_live_inference_reaches_both_eeg_pages_without_audio_assets(self):
        for index, task in enumerate(('fatigue', 'emotion')):
            with self.subTest(task=task):
                result = dict(origin='network', source='live:Z15', valid=True,
                    features=[.2], class_id=1, scores=[1, 3, 2], window_id='live-1')
                view = self.run_page({task: result}, index)
                self.assertTrue(view['valid'])
                self.assertEqual(view['source'], 'live:Z15')
                self.assertEqual(view['scores'], [1, 3, 2])
                self.assertEqual(view['task'], task)

    def test_absent_or_old_local_recording_shows_waiting_with_cleared_results(self):
        for status in ({}, {'fatigue': dict(origin='local', valid=True,
                source='recorded:LEMON_classifier_features', features=[.2],
                class_id=2, scores=[1, 2, 4])}):
            with self.subTest(status=status):
                view = self.run_page(status)
                self.assertFalse(view['valid'])
                self.assertEqual(view['source'], 'live:Z15')
                self.assertEqual(view['state'], 'waiting_for_live_eeg')
                self.assertIsNone(view['class_id'])
                self.assertIsNone(view['scores'])
                self.assertEqual(view['features'], [])

    def test_live_eeg_does_not_require_recorded_audio_assets(self):
        view = self.run_page({}, audio_assets=False)
        self.assertEqual(view['state'], 'waiting_for_live_eeg')


if __name__ == '__main__':
    unittest.main()

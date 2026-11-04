"""Exercise the public EEG entry with the real read-only bridge and no board."""
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
VISION = ROOT / 'src/workspace/integrations/vision_demo'
EEG = ROOT / 'src/workspace/integrations/eeg_demo/runtime'
sys.path[:0] = [str(VISION), str(EEG)]

import vision_demo.signal_runtime as runtime
from eeg_demo_bridge import CAP, DemoBridge


class LiveEntryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.clock = [100.]
        self.status = dict(stale=False, fatigue=dict(
            source='cyton_usb', channel_map=CAP, seq=1, valid=True,
            level='normal', score=.1, state='prediction'))
        self.telemetry = dict(stale=False, data_age_seconds=0., telemetry=dict(
            channels=CAP, real=True, samples=[[1.] * 8] * 10,
            raw_samples=[[2.] * 8] * 10, sample_index=2500, sample_rate_hz=250))
        self.bridge = DemoBridge(fetch=lambda path: self.status if path == '/api/status'
                                 else self.telemetry, clock=lambda: self.clock[0],
                                 autostart=False)
        stack = self.enterContext(ExitStack())
        original = runtime.Path
        folder = self.folder

        class ModulePath:
            def resolve(self):
                return self

            @property
            def parent(self):
                return folder

        stack.enter_context(patch.object(runtime, 'Path', side_effect=lambda value:
            ModulePath() if str(value).endswith('signal_runtime.py') else original(value)))
        stack.enter_context(patch('eeg_demo_bridge.DemoBridge', return_value=self.bridge))
        stack.enter_context(patch.object(runtime, 'SignalPresenter'))

    def make_runtime(self):
        result = runtime.SignalRuntime(None, {'enabled_signal_pages': ('fatigue', 'emotion')})
        self.addCleanup(result.close)
        return result

    def request(self, mode, request_id):
        (self.folder / 'source_selection.json').write_text(
            json.dumps(dict(mode=mode, request_id=request_id)), encoding='utf-8')

    def test_live_starts_without_any_recorded_assets_and_waits_for_receiver(self):
        signal = self.make_runtime()
        signal.next()
        signal.service(100.)
        self.assertEqual(signal.source.mode, 'live')
        self.assertEqual(signal.frame['origin'], 'live')
        self.assertFalse(signal.frame['ok'])
        self.assertEqual(signal.frame['raw'], [])

    def test_received_live_samples_survive_page_change_and_expiry_clears_results(self):
        self.bridge.refresh()
        signal = self.make_runtime()
        self.assertEqual(signal.next(), 'fatigue')
        signal.service(100.)
        self.assertTrue(signal.frame['ok'])
        self.assertEqual(signal.frame['origin'], 'live')
        self.assertEqual(signal.frame['raw'], self.telemetry['telemetry']['raw_samples'])
        self.assertEqual(signal.frame['fatigue']['level'], 'normal')
        self.assertEqual(signal.next(), 'emotion')
        signal.service(100.1)
        self.assertEqual(signal.frame['position_seconds'], 10.)
        self.clock[0] = 104.
        signal.service(104.)
        self.assertFalse(signal.frame['ok'])
        self.assertEqual(signal.frame['raw'], [])
        self.assertIsNone(signal.frame['fatigue'])
        self.assertEqual(signal.source.mode, 'live')

    def test_only_explicit_replay_request_loads_recording_and_live_can_resume(self):
        class Recording:
            def snapshot(self, position):
                return dict(origin='replay', stale=True, reason='fixture', position_seconds=position)

        with patch.object(runtime, 'PublicReplay', return_value=Recording()) as load:
            signal = self.make_runtime()
            signal.next()
            signal.service(100.)
            load.assert_not_called()
            self.request('replay', 'first')
            signal.service(101.)
            load.assert_called_once()
            self.assertEqual(signal.source.mode, 'replay')
            signal.next()
            signal.service(102.)
            load.assert_called_once()
            self.assertEqual(signal.source.started, 101.)
            self.request('live', 'second')
            signal.service(103.)
            self.assertEqual(signal.source.mode, 'live')
            self.assertEqual(signal.frame['origin'], 'live')
            signal.leave()
            self.assertEqual(signal.source.mode, 'live')

    def test_missing_requested_recording_keeps_live_available(self):
        self.bridge.refresh()
        signal = self.make_runtime()
        signal.next()
        signal.service(100.)
        self.request('replay', 'missing')
        signal.service(101.)
        self.assertEqual(signal.source.mode, 'live')
        self.assertTrue(signal.frame['ok'])
        self.assertTrue(signal.error)

    def test_local_source_command_accepts_live_without_replay_materials(self):
        media = self.folder / 'vision_demo'
        media.mkdir()
        (media / 'signal_runtime.py').write_text('# installed entry\n', encoding='utf-8')
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B',
            str(VISION / 'select_signal_source.py'), '--media-root', str(self.folder), 'live'],
            capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        request = json.loads((media / 'source_selection.json').read_text(encoding='utf-8'))
        self.assertEqual(request['mode'], 'live')
        self.assertTrue(request['request_id'])


if __name__ == '__main__':
    unittest.main()

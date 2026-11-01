"""No-device checks of cue timing, reject paths, and local HTTP contract."""
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from guardianloop_web import make_handler
from ssvep_cued import CuedSSVEPSession


class Clock:
    def __init__(self):
        self.value = 100.

    def __call__(self):
        return self.value


class CuedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.temp.name)/'cued.jsonl'
        self.clock = Clock()
        self.cue = CuedSSVEPSession(self.clock, self.log_path, lambda:1000.,
                                   boot_id='testboot')
        self.trial = self.cue.command({'action':'start', 'target_hz':10})
        self.token = self.trial['id']

    def tearDown(self):
        self.temp.cleanup()

    def command(self, action, **kwargs):
        return self.cue.command({'action':action, 'id':self.token, **kwargs})

    def shadow(self, hz=10, end=700, source='live', state='candidate_only', stale=False):
        return dict(stale=stale, live=dict(source=source, state=state,
                    valid=state=='candidate_only', frequency_hz=hz,
                    updated_monotonic=self.clock.value, input_age_seconds=0,
                    window_end_index_exclusive=end))

    def ready(self):
        self.command('presented', browser_onset_ms=500., browser_send_ms=501.,
                     browser_wall_ms=123456789.)
        for seconds in (1, 2, 3):
            self.clock.value += 1
            self.command('heartbeat', frame_count=60*seconds, duration_ms=1000*seconds,
                         max_gap_ms=17, poor_frames=0, display_hz=10)

    def test_cue_match_requires_three_distinct_adjacent_windows(self):
        self.ready()
        self.assertEqual(self.cue.observe(self.shadow(end=700))['streak'], 1)
        self.assertEqual(self.cue.observe(self.shadow(end=700))['streak'], 1)
        self.assertEqual(self.cue.observe(self.shadow(end=800))['streak'], 1)
        self.assertEqual(self.cue.observe(self.shadow(end=850))['streak'], 2)
        self.assertTrue(self.cue.observe(self.shadow(end=900))['accepted'])
        self.assertFalse(self.cue.observe(self.shadow(end=950, stale=True))['accepted'])
        self.command('stop')
        rows = [json.loads(line) for line in self.log_path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(rows[0]['event'], 'trial_start')
        self.assertEqual(rows[1]['event'], 'presentation_receipt')
        self.assertEqual(rows[1]['browser_onset_ms'], 500)
        self.assertEqual(rows[1]['browser_wall_ms'], 123456789)
        self.assertEqual(rows[1]['board_boot_id'], 'testboot')
        snapshots = [row for row in rows if row['event'] == 'shadow_snapshot']
        self.assertEqual([row['window_end_index_exclusive'] for row in snapshots], [700,800,850,900,950])
        self.assertEqual(snapshots[1]['missed_window_hops_since_last_observation'], 1)
        self.assertEqual(rows[-1]['event'], 'trial_end')
        self.assertTrue(rows[-1]['ever_matched'])
        self.assertEqual(rows[-1]['missed_window_hops_lower_bound'], 1)

    def test_reject_pre_cue_rest_wrong_source_and_bad_signal(self):
        self.assertFalse(self.cue.observe(self.shadow())['accepted'])
        self.ready()
        for data in (self.shadow(source='replay'), self.shadow(state='signal_invalid'),
                     self.shadow(hz=12), self.shadow(stale=True)):
            self.assertFalse(self.cue.observe(data)['accepted'])
        self.command('stop')
        self.assertFalse(self.cue.observe(self.shadow())['accepted'])
        self.cue.command({'action':'start', 'target_hz':0})
        token = self.cue.trial['id']
        self.cue.command({'action':'presented', 'id':token,
                          'browser_onset_ms':100., 'browser_send_ms':101.})
        for seconds in (1, 2, 3):
            self.clock.value += 1
            self.cue.command({'action':'heartbeat', 'id':token, 'frame_count':60*seconds,
                              'duration_ms':1000*seconds, 'max_gap_ms':17, 'poor_frames':0,
                              'display_hz':0})
        self.assertEqual(self.cue.observe(self.shadow())['reason'], 'rest_no_control')

    def test_missing_heartbeat_and_bad_frame_timing(self):
        self.ready()
        self.command('heartbeat', frame_count=180, duration_ms=3000,
                     max_gap_ms=80, poor_frames=3, display_hz=10)
        self.assertEqual(self.cue.observe(self.shadow())['reason'], 'display_timing_unreliable')
        self.clock.value += 2
        self.assertEqual(self.cue.observe(self.shadow())['reason'], 'display_heartbeat_lost')
        self.assertFalse(self.cue.observe(self.shadow())['accepted'])

    def test_reject_invalid_target_or_token(self):
        with self.assertRaises(ValueError):
            self.cue.command({'action':'start', 'target_hz':11})
        with self.assertRaises(ValueError):
            self.cue.command({'action':'presented', 'id':'wrong'})
        with self.assertRaises(ValueError):
            self.command('presented', browser_onset_ms=100, browser_send_ms=99)

    def test_log_failure_refuses_to_start_trial(self):
        cue = CuedSSVEPSession(self.clock, Path(self.temp.name)/'missing'/'trials.jsonl')
        with self.assertRaises(OSError):
            cue.command({'action':'start', 'target_hz':10})
        self.assertIsNone(cue.trial)

    def test_display_timing_abort_is_audited(self):
        with self.assertRaises(ValueError):
            self.command('stop', stop_reason='arbitrary')
        self.assertEqual(self.command('stop', stop_reason='display_timing_unreliable')['reason'],
                         'display_timing_unreliable')
        rows = [json.loads(line) for line in self.log_path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(rows[-1]['event'], 'trial_end')
        self.assertEqual(rows[-1]['reason'], 'display_timing_unreliable')


class WebTests(unittest.TestCase):
    def test_http_route_and_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(
                root/'status.json', root/'telemetry.json', 3,
                ssvep_live_path=root/'live.json', ssvep_replay_path=root/'replay.json',
                cued_session=CuedSSVEPSession(log_path=root/'cue.jsonl')))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host = f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(host+'/ssvep-cued') as response:
                    page = response.read().decode()
                    self.assertIn('8 秒以内', page)
                    self.assertIn('测浏览器帧时序（不闪烁', page)
                    self.assertIn('不是屏幕发光实测', page)
                    self.assertIn('每半周期 12/10 帧', page)
                def post(payload, origin=host):
                    data = json.dumps(payload).encode()
                    headers = {'Content-Type':'application/json'}
                    if origin is not None:
                        headers['Origin'] = origin
                    with urlopen(Request(host+'/api/ssvep-cue', data=data, headers=headers)) as response:
                        return json.load(response)
                with self.assertRaises(HTTPError) as error:
                    post({'action':'start', 'target_hz':10}, origin=None)
                self.assertEqual(error.exception.code, 403)
                started = post({'action':'start', 'target_hz':10})
                self.assertEqual(started['state'], 'awaiting_presentation')
                self.assertFalse(started['control_enabled'])
                post({'action':'presented', 'id':started['id'],
                      'browser_onset_ms':100, 'browser_send_ms':101})
                with urlopen(host+'/api/ssvep-cue') as response:
                    state = json.load(response)
                self.assertFalse(state['accepted'])
                self.assertEqual(state['state'], 'active')
                self.assertEqual(len((root/'cue.jsonl').read_text(encoding='utf-8').splitlines()), 2)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()

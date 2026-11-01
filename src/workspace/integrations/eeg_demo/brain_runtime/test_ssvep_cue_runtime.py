"""No-device tests: producer windows own matches, never web polling frequency."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

from guardianloop_web import make_handler
from ssvep_cue_runtime import SSVEPCueBridge, SSVEPCueRuntime
from ssvep_shadow import CHANNELS, SSVEPShadow
from ssvep_hdmi import SCAN_PERIOD, pattern
from cyton_trial_recorder import atomic_json

HERE = Path(__file__).resolve().parent
ASSETS = HERE if (HERE/'ssvep_causal_protocol.json').exists() else HERE.parent/'eeg_apps_z15'
SOS = (HERE/'ssvep_candidate_sos.npy' if (HERE/'ssvep_candidate_sos.npy').exists()
       else ASSETS/'output/ssvep_causal_20260926/candidate_sos.npy')


class RuntimeTests(unittest.TestCase):
    def test_input_preparation_has_ownership_expiry_and_never_starts_stimulus(self):
        self.owner.page_policy_path=self.root/'page.json'
        self.assertFalse(self.bridge.snapshot()['input']['preparation']['active'])
        self.assertFalse(self.owner.page_policy_path.exists())
        self.owner.latest=dict(self.event(),state='no_data',valid=False,reason='page_task_suspended',
                               updated_monotonic=self.now-400)
        view=self.bridge.snapshot()['input']
        self.assertEqual(view['state'],'suspended');self.assertIsNone(view['age_seconds'])
        with self.assertRaises(ValueError):self.owner.command({'action':'input_prepare'})
        ready=self.owner.command({'action':'input_prepare','consent':True})
        token=ready['input']['preparation']['token']
        self.assertTrue(ready['input']['preparation']['active'])
        self.assertNotEqual(ready['state'],'active')
        from page_policy import browser_input_path
        row=json.loads(browser_input_path(self.owner.page_policy_path).read_text())
        self.assertTrue(row['enabled']);self.assertFalse(row['physical_output_enabled'])
        with self.assertRaises(ValueError):
            self.owner.command({'action':'input_heartbeat','token':'other'})
        self.now+=1
        self.owner.free_command({'action':'input_heartbeat','token':token})
        self.now+=3.1
        self.assertFalse(self.bridge.snapshot()['input']['preparation']['active'])
        with self.assertRaises(ValueError):
            self.owner.command({'action':'input_heartbeat','token':token})
        self.owner.free_command({'action':'input_release','token':token})
        self.assertFalse(json.loads(browser_input_path(self.owner.page_policy_path).read_text())['enabled'])
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = 100.0
        self.owner = SSVEPCueRuntime(self.root/'cue.jsonl', port=0, clock=lambda: self.now)
        self.bridge = SSVEPCueBridge(self.owner.server.server_port)

    def tearDown(self):
        self.owner.close()
        self.temp.cleanup()

    def event(self, index=1000, hz=12, **fields):
        return dict(source='live', state='candidate_only', valid=True,
                    frequency_hz=hz, updated_monotonic=self.now, input_age_seconds=0.0,
                    window_end_index_exclusive=index, quality={'hard_bad': False}, **fields)

    def start(self, target=12):
        self.owner.observe(self.event())
        started = self.bridge.command({'action':'start', 'target_hz':target})
        self.token = started['id']
        self.bridge.command({'action':'presented', 'id':self.token,
                             'browser_onset_ms':0, 'browser_send_ms':0})
        return started

    def heartbeat(self, elapsed=3000, hz=12):
        self.owner.command({'action':'heartbeat', 'id':self.token,
                            'frame_count':elapsed*240//1000, 'duration_ms':elapsed,
                            'max_gap_ms':4.2, 'poor_frames':0, 'display_hz':hz})

    def ready(self, target=12):
        self.start(target)
        for second in (1, 2, 3):
            self.now += 1
            self.heartbeat(second*1000, target)

    def match(self):
        for offset in range(3):
            self.now += .2
            self.owner.observe(self.event(1000+offset*50))

    def test_match_without_any_browser_get_and_repeated_get_does_not_count(self):
        self.ready()
        self.match()
        before = self.bridge.snapshot()
        self.assertTrue(before['accepted'])
        self.assertEqual(before['observed_windows'], 3)
        for _ in range(15):
            after = self.bridge.snapshot()
            self.assertEqual(after['observed_windows'], 3)
            self.assertEqual(after['streak'], 3)
            self.assertTrue(after['accepted'])

    def test_poll_intervals_do_not_change_producer_decisions(self):
        self.ready()
        for index in range(20):
            self.now += .2
            if index % 2 == 0:
                self.heartbeat(3200+index*200)
            self.owner.observe(self.event(1000+index*50))
            if index % 3 == 0:
                state = self.bridge.snapshot()
                self.assertEqual(state['observed_windows'], index+1)
        result = self.bridge.snapshot()
        self.assertEqual(result['streak'], 20)
        self.assertTrue(result['accepted'])
        rows = [json.loads(line) for line in (self.root/'cue.jsonl').read_text().splitlines()]
        snapshots = [row for row in rows if row['event']=='shadow_snapshot']
        self.assertEqual(len(snapshots), 20)
        self.assertTrue(all(not row['snapshot_polling_may_skip_windows'] for row in snapshots))
        self.assertEqual(result['missed_window_hops_lower_bound'], 0)

    def test_duplicates_gaps_and_out_of_order_revoke_or_restart_streak(self):
        self.ready()
        self.owner.observe(self.event(1000))
        for _ in range(3):
            self.owner.observe(self.event(1000))
        self.assertEqual(self.bridge.snapshot()['streak'], 1)
        self.now += .2
        self.owner.observe(self.event(1100))
        self.assertEqual(self.bridge.snapshot()['streak'], 1)
        for index in (1150, 1200):
            self.now += .2
            self.owner.observe(self.event(index))
        self.assertTrue(self.bridge.snapshot()['accepted'])
        self.owner.observe(self.event(1150))
        result = self.bridge.snapshot()
        self.assertFalse(result['accepted'])
        self.assertEqual(result['reason'], 'out_of_order_window')

    def test_stale_future_replay_and_hard_bad_revoke(self):
        for invalid in ('stale', 'future', 'replay', 'hard_bad'):
            with self.subTest(invalid=invalid):
                if hasattr(self, 'token'):
                    self.owner.command({'action':'stop', 'id':self.token})
                self.ready()
                self.match()
                event = self.event(1150)
                if invalid=='stale': event['updated_monotonic'] -= 1
                elif invalid=='future': event['updated_monotonic'] += 1
                elif invalid=='replay': event['source'] = 'replay'
                else: event['quality'] = {'hard_bad': True}
                self.owner.observe(event)
                self.assertFalse(self.bridge.snapshot()['accepted'])

    def test_no_data_or_replay_cannot_start(self):
        for event in (None, dict(self.event(), source='replay'),
                      dict(self.event(), state='no_data', valid=False)):
            self.owner.latest = event
            with self.assertRaises(ValueError):
                self.bridge.command({'action':'start', 'target_hz':12})

    def test_input_diagnostics_explain_backlog_and_hide_stale_scores(self):
        self.owner.observe(self.event(scores=[.1,.2,.7,.3]))
        view=self.bridge.free_snapshot()['input']
        self.assertTrue(view['ready'])
        self.assertEqual(view['top_score'],.7)
        self.assertAlmostEqual(view['margin'],.4)
        self.owner.observe(dict(self.event(),state='no_data',valid=False,
                                input_age_seconds=.6,reason='input_backlog'))
        view=self.bridge.snapshot()['input']
        self.assertFalse(view['ready'])
        self.assertEqual(view['reason'],'input_backlog')
        self.assertIsNone(view['scores'])
        self.owner.latest=dict(self.event(),updated_monotonic=None)
        self.assertFalse(self.bridge.snapshot()['input']['ready'])

    def test_demo_starts_without_recording_but_explicit_requirement_is_kept(self):
        self.owner.record_status_path=self.root/'record_status.json'
        self.owner.observe(self.event())
        started=self.bridge.command({'action':'start','target_hz':12,'require_raw_recording':False})
        self.assertIsNone(started['raw_recording'])
        self.bridge.command({'action':'stop','id':started['id']})
        with self.assertRaisesRegex(ValueError,'普通演示'):
            self.bridge.command({'action':'start','target_hz':12,'require_raw_recording':True})

    def test_raw_requirement_cannot_be_forged_and_records_linked_trial(self):
        self.owner.observe(self.event())
        self.owner.record_status_path=self.root/'record_status.json'
        with self.assertRaises(ValueError):
            self.bridge.command({'action':'start','target_hz':12,'require_raw_recording':True,
                                 'raw_recording':{'trial_id':'forged','path':'forged'}})
        atomic_json(self.owner.record_status_path, dict(state='recording',task='ssvep',
            trial_id='1234567890abcdef',path=str(self.root/'raw'),samples=250,
            elapsed_seconds=1,updated_monotonic=self.now))
        trial=self.bridge.command({'action':'start','target_hz':12,'require_raw_recording':True})
        self.assertEqual(trial['raw_recording']['trial_id'],'1234567890abcdef')
        row=json.loads((self.root/'cue.jsonl').read_text().splitlines()[0])
        self.assertTrue(row['raw_eeg_recorded'])
        self.assertFalse(row['raw_capture_completeness_verified'])
        self.assertEqual(row['raw_recording_id'],'1234567890abcdef')
        atomic_json(self.owner.record_status_path, dict(state='complete',task='ssvep',
                                                      updated_monotonic=self.now))
        ended=self.bridge.snapshot()
        self.assertEqual(ended['reason'],'raw_recording_unavailable')
        self.assertFalse(ended['accepted'])

    def test_stale_raw_recording_and_other_task_do_not_count_as_sync(self):
        self.owner.observe(self.event())
        self.owner.record_status_path=self.root/'record_status.json'
        for fields in ({'updated_monotonic':self.now-2.1}, {'task':'emotion'},
                       {'updated_monotonic':self.now+1}):
            atomic_json(self.owner.record_status_path, dict(dict(
                state='recording',task='ssvep',trial_id='1234567890abcdef',
                updated_monotonic=self.now),**fields))
            with self.assertRaises(ValueError):
                self.bridge.command({'action':'start','target_hz':12,'require_raw_recording':True})

    def test_data_timeout_revokes_even_with_a_fresh_display_heartbeat(self):
        self.ready()
        self.match()
        self.now += .51
        self.heartbeat()
        state = self.bridge.snapshot()
        self.assertFalse(state['accepted'])
        self.assertIsNone(state['result'])

    def test_late_heartbeat_cannot_resurrect_a_trial(self):
        self.ready()
        self.match()
        self.now += 1.51
        with self.assertRaises(ValueError): self.heartbeat()
        self.assertEqual(self.bridge.snapshot()['reason'], 'display_heartbeat_lost')

    def test_stop_and_rest_never_emit_control(self):
        self.ready()
        self.match()
        self.bridge.command({'action':'stop', 'id':self.token})
        self.owner.observe(self.event(1150))
        self.assertFalse(self.bridge.snapshot()['accepted'])
        self.assertIsNone(self.bridge.snapshot()['observed_hz'])
        self.ready(target=0)
        self.owner.observe(self.event())
        self.assertEqual(self.bridge.snapshot()['reason'], 'rest_no_control')
        self.assertFalse(self.bridge.snapshot()['control_enabled'])

    def test_audit_io_failure_disables_cue_without_breaking_callback(self):
        self.ready()
        self.match()
        self.owner.session.log_path = self.root/'missing'/'cue.jsonl'
        self.owner.observe(self.event(1150))
        self.assertEqual(self.bridge.snapshot()['reason'], 'cue_audit_io_failed')
        self.assertFalse(self.bridge.snapshot()['accepted'])
        with self.assertRaises(OSError): self.bridge.command({'action':'heartbeat', 'id':self.token})

    def test_backend_down_has_no_cached_result(self):
        self.ready()
        self.match()
        self.assertTrue(self.bridge.snapshot()['accepted'])
        self.owner.close()
        self.assertFalse(self.bridge.snapshot()['accepted'])
        self.assertIsNone(self.bridge.snapshot()['result'])

    def test_shadow_callback_observes_every_real_computed_window(self):
        with patch('ssvep_shadow.time.monotonic', lambda: self.now):
            shadow = SSVEPShadow(ASSETS/'ssvep_causal_protocol.json', SOS, CHANNELS,
                                source='live', status_path=self.root/'shadow.json',
                                event_sink=self.owner.observe)
            t = np.arange(2500)/250
            samples = np.zeros((len(t), 8))
            samples[:, 6] = 12*np.sin(2*np.pi*12*t) + np.sin(2*np.pi*17*t)
            samples[:, 7] = 9*np.sin(2*np.pi*12*t+.3) + np.sin(2*np.pi*19*t)
            for index in range(800):
                self.now = 100+index/250
                shadow.packet(samples[index], index%256, now=self.now)
            self.start()
            began = self.now
            for index in range(800, 2500):
                self.now = 100+index/250
                if index%100 == 0:
                    self.heartbeat(round((self.now-began)*1000))
                shadow.packet(samples[index], index%256, now=self.now)
            state = self.bridge.snapshot()
            self.assertTrue(state['accepted'])
            self.assertEqual(state['observed_hz'], 12)
            self.assertEqual(state['missed_window_hops_lower_bound'], 0)

    def test_public_web_get_is_read_only_and_checks_origin(self):
        self.ready()
        self.match()
        web = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(
            self.root/'primary.json', self.root/'telemetry.json', 3, cued_session=self.bridge))
        thread = threading.Thread(target=web.serve_forever, daemon=True)
        thread.start()
        url = 'http://127.0.0.1:%d/api/ssvep-cue' % web.server_port
        try:
            for _ in range(3):
                with urlopen(url) as reply:
                    self.assertEqual(json.load(reply)['streak'], 3)
            with self.assertRaises(HTTPError) as failure:
                urlopen(Request(url, data=b'{"action":"start","target_hz":12}',
                                headers={'Content-Type':'application/json'}))
            self.assertEqual(failure.exception.code, 403)
        finally:
            web.shutdown(); web.server_close(); thread.join(timeout=2)


class ReportConnectionTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.owner = SSVEPCueRuntime(log_path=None, port=0, clock=lambda: self.now)
        self.bridge = SSVEPCueBridge(self.owner.server.server_port)
        self.connections = 0
        accept = self.owner.server.get_request

        def counted_accept():
            result = accept()
            self.connections += 1
            return result

        self.owner.server.get_request = counted_accept
        self.owner.observe(dict(source='live', state='candidate_only', valid=True,
            frequency_hz=12, updated_monotonic=self.now, input_age_seconds=0.,
            window_end_index_exclusive=1000, quality={'hard_bad': False}))
        self.started = self.bridge.hdmi_command(dict(action='start', page_id=1,
            consent=True, frequencies=[8, 10, 12, 14]))
        self.identity = dict(id=self.started['id'], page_id=1)

    def tearDown(self):
        self.bridge._close_reports()
        self.owner.close()

    def presented(self):
        return self.bridge.hdmi_command(dict(self.identity, action='presented',
            origin_counter=0, active_index=0, presented_monotonic=100.))

    def latches(self, first, count=4):
        end = first + count - 1
        self.now = 100. + end * SCAN_PERIOD
        return [dict(counter_before=i-1, counter_after=i, target_counter=i,
            requested_index=i % 3, active_index=i % 3, pattern_mask=pattern(i),
            dma_status=0, ack_monotonic=100. + i * SCAN_PERIOD)
            for i in range(first, end+1)]

    def test_reports_share_one_connection_and_stop_closes_it(self):
        before = self.connections
        self.presented()
        for first in (1, 5, 9):
            reply = self.bridge.hdmi_command(dict(self.identity, action='heartbeat',
                                                latches=self.latches(first)))
        self.assertEqual(reply['display_timing']['scans'], 12)
        self.assertEqual(self.connections-before, 1)
        self.assertIsNotNone(self.bridge.report_connection.sock)
        stopped = self.bridge.hdmi_command(dict(self.identity, action='stop'))
        self.assertEqual(stopped['state'], 'stopped')
        self.assertIsNone(self.bridge.report_connection.sock)

    def test_rejected_latch_is_not_retried_and_connection_is_closed(self):
        self.presented()
        before = self.connections
        with self.assertRaisesRegex(ValueError, 'Skipped'):
            self.bridge.hdmi_command(dict(self.identity, action='heartbeat',
                                         latches=self.latches(2)))
        self.assertEqual(self.connections, before)
        self.assertEqual(self.owner.hdmi_session.evidence.scans, 0)
        self.assertIsNotNone(self.owner.hdmi_session.evidence.failed)
        self.assertIsNone(self.bridge.report_connection.sock)

    def test_closed_backend_cannot_keep_serving_existing_report_socket(self):
        self.presented()
        rows = self.latches(1)
        self.owner.close()
        with self.assertRaises(OSError):
            self.bridge.hdmi_command(dict(self.identity, action='heartbeat', latches=rows))
        self.assertEqual(self.owner.hdmi_session.evidence.scans, 0)
        self.assertIsNone(self.bridge.report_connection.sock)

    def test_source_validation_also_applies_to_persistent_replies(self):
        self.owner.hdmi_session._snapshot = lambda now: dict(source='replay',
            state_owner='acquisition', observation_mode='producer_callbacks',
            control_enabled=False)
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.presented()
        self.assertIsNone(self.bridge.report_connection.sock)


if __name__ == '__main__':
    unittest.main()

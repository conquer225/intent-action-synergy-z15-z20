import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

from mi_cued import CuedMISession
from mi_cued_server import make_handler


class Clock:
    def __init__(self):
        self.value = 100.

    def __call__(self):
        return self.value


class Model:
    def __init__(self, score=(1., -1.)):
        self.calls = 0
        self.score = score

    def logits(self, values):
        assert values.shape == (1, 8, 500)
        self.calls += 1
        return np.array([self.score])


class CuedTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.model = Clock(), Model()
        self.session = CuedMISession(self.model, clock=self.clock)
        self.count = 0

    def feed(self, count=50, gain=10, block=50):
        for offset in range(0, count, block):
            n = min(block, count-offset)
            samples = np.arange(self.count, self.count+n)
            waves = gain * np.sin(2*np.pi*samples[:, None]/250*np.arange(8, 16)[None])
            self.clock.value += n/250
            self.session.feed(waves, samples % 256)
            self.count += n
            if self.session.trial and self.session.trial['state'] == 'active':
                self.command('heartbeat')

    def command(self, action, **fields):
        return self.session.command(dict(action=action, id=self.session.trial['id'], **fields))

    def ready(self, target='left'):
        self.feed(750)
        self.session.command(dict(action='start', target=target))
        self.command('presented', browser_onset_ms=100, browser_send_ms=101)

    def predict(self, target='left'):
        self.ready(target)
        self.feed(650)
        return self.session.snapshot()

    def test_idle_and_rest_do_not_call_model(self):
        self.feed(1000)
        self.assertEqual(self.model.calls, 0)
        self.session.command(dict(action='start', target='rest'))
        self.command('presented', browser_onset_ms=100, browser_send_ms=101)
        self.feed(1000)
        self.assertIsNone(self.session.snapshot()['result'])
        self.assertEqual(self.model.calls, 0)

    def test_one_complete_window_only_and_not_forced_to_cue(self):
        self.ready('right')
        self.feed(600)
        self.assertEqual(self.model.calls, 0)
        self.feed(25)
        result = self.session.snapshot()['result']
        self.assertEqual(result['label'], 'left')
        self.assertFalse(result['matches_cue'])
        self.assertEqual(result['window_end_exclusive']-result['window_start'], 500)
        self.feed(100)
        self.assertEqual(self.model.calls, 1)
        self.assertFalse(result['control_enabled'])

    def test_missing_model_and_warmup_refused(self):
        for session, expected in ((CuedMISession(clock=self.clock), 'model_unavailable'),
                                  (self.session, 'filter_warmup_required')):
            session.command(dict(action='start', target='left'))
            result = session.command(dict(action='presented', id=session.trial['id'],
                                          browser_onset_ms=1, browser_send_ms=2))
            self.assertEqual(result['reason'], expected)
            self.assertIsNone(result['result'])

    def test_stop_and_page_hidden_withdraw(self):
        for reason in ('user_stopped', 'page_hidden', 'page_closed'):
            if self.session.trial:
                self.command('stop')
            self.predict()
            self.assertIsNotNone(self.session.snapshot()['result'])
            self.command('stop', reason=reason)
            self.assertIsNone(self.session.snapshot()['result'])

    def test_disconnect_resets_and_requires_new_warmup(self):
        self.predict()
        self.session.disconnect()
        state = self.session.snapshot()
        self.assertIsNone(state['result'])
        self.assertEqual(state['received_samples'], 0)
        self.session.command(dict(action='start', target='left'))
        state = self.command('presented', browser_onset_ms=1, browser_send_ms=2)
        self.assertEqual(state['reason'], 'filter_warmup_required')

    def test_sequence_duplicate_and_skip_withdraw(self):
        for advance in (0, 2):
            self.session = CuedMISession(self.model, clock=self.clock)
            self.count = 0
            self.predict()
            seq = (self.session.previous_sequence+advance) % 256
            state = self.session.feed(np.ones((1,8)), np.array([seq]))
            self.assertEqual(state['reason'], 'sequence_gap_or_stall')
            self.assertIsNone(state['result'])

    def test_bad_internal_sequences(self):
        self.ready()
        state = self.session.feed(np.ones((3,8)), np.array([238,239,241]))
        self.assertEqual(state['reason'], 'sequence_gap_or_stall')
        self.assertEqual(self.model.calls, 0)

    def test_stale_result_heartbeat_and_trial_timeout(self):
        self.predict()
        self.clock.value += .51
        self.assertEqual(self.session.snapshot()['reason'], 'no_fresh_data')
        self.assertIsNone(self.session.snapshot()['result'])
        self.session = CuedMISession(self.model, clock=self.clock)
        self.count = 0
        self.ready()
        self.clock.value += 1.51
        self.assertEqual(self.session.snapshot()['reason'], 'browser_heartbeat_lost')
        self.session.command(dict(action='start', target='rest'))
        self.clock.value += 8
        self.assertEqual(self.session.snapshot()['reason'], 'trial_timeout')

    def test_late_batch_and_future_clock_refused(self):
        for offset in (-1, 1):
            self.session = CuedMISession(self.model, clock=self.clock)
            self.count = 0
            self.ready()
            result = self.session.feed(np.ones((1,8)), np.array([self.count % 256]),
                                       received_monotonic=self.clock.value+offset)
            self.assertEqual(result['reason'], 'late_or_reordered_batch')
            self.assertIsNone(result['result'])

    def test_terminal_heartbeat_reports_reason_without_reactivating(self):
        self.ready('rest')
        heartbeat = self.session.trial['heartbeat']
        self.clock.value += 8
        result = self.command('heartbeat')
        self.assertEqual(result['reason'], 'trial_timeout')
        self.assertEqual(result['state'], 'rejected')
        self.assertIsNone(result['result'])
        self.assertEqual(self.session.trial['heartbeat'], heartbeat)
        self.command('stop')
        self.assertEqual(self.command('heartbeat')['state'], 'stopped')

    def test_invalid_shape_nan_and_sequence_type_withdraw(self):
        self.predict()
        for values, sequences in ((np.ones((2,7)), np.array([0,1])),
                                   (np.full((2,8), np.nan), np.array([0,1])),
                                   (np.ones((2,8)), np.array([0.,1.]))):
            with self.assertRaises(ValueError):
                self.session.feed(values, sequences)
            self.assertIsNone(self.session.snapshot()['result'])

    def test_quality_flatline_and_excess_amplitude_rejected(self):
        self.ready()
        for _ in range(13):
            self.clock.value += .2
            count = self.count
            state = self.session.feed(np.zeros((50,8)), np.arange(count,count+50)%256)
            self.count += 50
            if state['state'] == 'active':
                self.command('heartbeat')
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(state['reason'], 'signal_invalid')
        self.session = CuedMISession(self.model, clock=self.clock)
        self.count = 0
        self.ready()
        self.feed(650, gain=1000)
        self.assertEqual(self.session.snapshot()['reason'], 'signal_invalid')
        self.assertEqual(self.model.calls, 0)

    def test_bad_quality_after_result_revokes(self):
        self.predict()
        self.feed(50, gain=2000)
        self.assertEqual(self.session.snapshot()['reason'], 'signal_invalid')
        self.assertIsNone(self.session.snapshot()['result'])

    def test_replay_never_disguised_as_live(self):
        self.session = CuedMISession(self.model, clock=self.clock, source='replay')
        state = self.predict()
        self.assertEqual(state['source'], 'replay')
        self.assertEqual(state['result']['source'], 'replay')
        self.assertFalse(state['production_eligible'])

    def test_old_token_target_timestamps_and_duplicate_start_rejected(self):
        self.ready()
        for request in (dict(action='start',target='finger'), dict(action='start',target='left'),
                        dict(action='heartbeat',id='old'),
                        dict(action='presented',id=self.session.trial['id'],browser_onset_ms=2,browser_send_ms=1)):
            with self.assertRaises(ValueError):
                self.session.command(request)

    def test_log_has_labeled_source_and_revocation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'events.jsonl'
            self.session = CuedMISession(self.model, clock=self.clock, source='replay', log_path=path)
            self.predict()
            self.command('stop')
            rows = [json.loads(row) for row in path.read_text().splitlines()]
            self.assertEqual([row['event'] for row in rows],
                             ['trial_start','presentation_receipt','candidate','withdraw'])
            self.assertTrue(all(row['source']=='replay' and not row['control_enabled'] for row in rows))

    def test_block_size_does_not_change_continuous_filters(self):
        values = np.random.default_rng(42).normal(size=(2000,8))
        outputs = []
        for width in (1,25,50,250):
            session = CuedMISession(clock=self.clock)
            for start in range(0,len(values),width):
                session.feed(values[start:start+width], np.arange(start,start+width)%256)
            outputs.append(session.filtered.copy())
        for actual in outputs[1:]:
            np.testing.assert_allclose(actual, outputs[0], rtol=0, atol=1e-10)

    def test_audit_failure_is_not_a_valid_prediction(self):
        with tempfile.TemporaryDirectory() as directory:
            self.session = CuedMISession(self.model, clock=self.clock,
                                         log_path=Path(directory)/'missing'/'events.jsonl')
            with self.assertRaises(OSError):
                self.session.command(dict(action='start',target='left'))
            self.assertIsNone(self.session.trial)
            self.session.log_path = None
            self.predict()
            self.session.log_path = Path(directory)/'missing'/'events.jsonl'
            with self.assertRaises(OSError):
                self.command('stop')
            self.assertIsNone(self.session.snapshot()['result'])
            self.assertEqual(self.session.index, 0)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.session = CuedMISession()
        self.server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(self.session))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, request, origin=None, path='/api/mi-cue'):
        return urlopen(Request(self.url+path, data=json.dumps(request).encode(),
                       headers={'Content-Type':'application/json',
                                'Origin':origin or self.url}), timeout=2)

    def test_page_status_and_model_unavailable(self):
        with urlopen(self.url+'/mi-cued', timeout=2) as response:
            self.assertIn('休息（禁用推理）',response.read().decode())
        with urlopen(self.url+'/api/mi-cue', timeout=2) as response:
            self.assertEqual(json.load(response)['input_state'],'no_data')
        with self.post(dict(action='start',target='left')) as response:
            trial = json.load(response)
        with self.post(dict(action='presented',id=trial['id'],browser_onset_ms=1,browser_send_ms=2)) as response:
            self.assertEqual(json.load(response)['reason'],'model_unavailable')

    def test_cross_origin_unknown_feed_and_bad_object_refused(self):
        for request, origin, path, code in ((dict(action='start',target='left'),'http://evil.local','/api/mi-cue',403),
                                          (dict(action='feed'),self.url,'/api/mi-feed',404),
                                          ([],self.url,'/api/mi-cue',400),
                                          (dict(action='predict',label='right'),self.url,'/api/mi-cue',400)):
            with self.assertRaises(HTTPError) as error:
                self.post(request,origin,path)
            self.assertEqual(error.exception.code, code)
        self.assertIsNone(self.session.snapshot()['result'])


if __name__ == '__main__':
    unittest.main()

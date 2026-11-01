import json
from http.server import ThreadingHTTPServer
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

from mi_rms_virtual_replay import RMSReplayApp, handler_for, page_bytes
from test_mi_cued import Model


class RMSVirtualTests(unittest.TestCase):
    def setUp(self):
        self.entered = threading.Event()

        def wait_for_stop(app, raw, seq, stop):
            self.entered.set()
            stop.wait(2)
            app.disconnect('replay_eof')

        raw = np.zeros((750, 8))
        self.app = RMSReplayApp(Model(), raw, np.arange(750)%256,
                                model_sha256='model-test', input_sha256='record-test',
                                feeder=wait_for_stop)

    def tearDown(self):
        self.app.close()

    def test_manual_start_no_live_source_or_automatic_repeat(self):
        state = self.app.snapshot()
        self.assertEqual(state['source'], 'replay')
        self.assertEqual(state['replay']['state'], 'idle')
        self.assertFalse(state['replay']['auto_repeat'])
        self.assertFalse(state['control_enabled'])
        self.assertFalse(state['production_eligible'])
        self.assertFalse(state['candidate_model']['personal_accuracy_validated'])
        with self.assertRaises(ValueError):
            self.app.command(dict(action='start', target='left', virtual_control=True))
        self.app.command(dict(action='replay_start'))
        self.assertTrue(self.entered.wait(1))
        with self.assertRaises(ValueError):
            self.app.command(dict(action='replay_start'))
        with self.assertRaises(ValueError):
            self.app.command(dict(action='start', target='right'))
        self.assertEqual(self.app.session.model.calls, 0)

    def test_stop_and_restart_reset_filter_without_reusing_commands(self):
        self.app.command(dict(action='replay_start'))
        state = self.app.command(dict(action='replay_stop'))
        self.assertEqual(state['replay']['state'], 'stopped')
        self.assertEqual(state['received_samples'], 0)
        self.assertFalse(state['virtual_hand']['enabled'])
        self.assertIsNone(state['result'])
        self.assertIsNone(state['virtual_hand']['last_command'])
        state = self.app.command(dict(action='replay_start'))
        self.assertEqual(state['replay']['run'], 2)
        self.assertEqual(state['replay']['samples_sent'], 0)
        self.assertEqual(state['input_state'], 'no_data')

    def test_eof_and_progress_not_automatic_loop(self):
        def finish(app, raw, seq, stop):
            samples = np.arange(50)
            values = np.sin(samples[:, None]*np.arange(1, 9)[None]/10)
            app.feed(values, samples%256)
            app.disconnect('replay_eof')

        self.app.feeder = finish
        self.app.command(dict(action='replay_start'))
        self.app.worker.join(1)
        state = self.app.snapshot()
        self.assertEqual(state['replay']['state'], 'eof')
        self.assertEqual(state['replay']['samples_sent'], 50)
        self.assertEqual(state['replay']['run'], 1)
        self.assertEqual(state['input_state'], 'no_data')
        self.assertIsNone(state['result'])
        self.assertFalse(state['virtual_hand']['enabled'])

    def test_replay_cannot_upload_data_speed_or_answers(self):
        for fields in ({'label':'right'}, {'speed':100}, {'raw':[1]}, {'virtual_control':True}):
            with self.assertRaises(ValueError):
                self.app.command(dict(action='replay_start', **fields))
        with self.assertRaises(ValueError):
            self.app.command(dict(action='virtual_move', position_percent=100))

    def test_page_reuses_safety_client_and_identifies_recorded_input(self):
        page = page_bytes().decode('utf-8')
        self.assertEqual(page.count('id="replayStart"'), 1)
        self.assertEqual(page.count('id="virtualFingers"'), 1)
        self.assertIn('你的当前想象不会改变', page)
        self.assertIn("command.trial_id === trialId", page)
        self.assertIn("document.addEventListener('visibilitychange'", page)
        self.assertIn("reasons.replay_eof", page)

    def test_http_origin_and_endpoint_boundaries(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.app))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            with urlopen(base+'/mi-cued', timeout=2) as response:
                self.assertIn('共享 RMS', response.read().decode('utf-8'))
            with urlopen(base+'/api/mi-cue', timeout=2) as response:
                self.assertEqual(json.load(response)['replay']['state'], 'idle')
            request = Request(base+'/api/mi-cue', data=b'{"action":"replay_start"}',
                              headers={'Origin':'http://other.test','Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=2)
            self.assertEqual(error.exception.code, 403)
            request = Request(base+'/api/mi-cue', data=b'{"action":"replay_start","label":"right"}',
                              headers={'Origin':base,'Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=2)
            self.assertEqual(error.exception.code, 400)
            with self.assertRaises(HTTPError) as error:
                urlopen(base+'/api/actuator', timeout=2)
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)


if __name__ == '__main__':
    unittest.main()

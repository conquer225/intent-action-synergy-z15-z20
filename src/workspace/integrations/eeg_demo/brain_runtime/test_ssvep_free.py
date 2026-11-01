"""Exercise producer ownership, abstention, fault withdrawal and independent choices."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

from guardianloop_web import make_handler
from ssvep_cue_runtime import SSVEPCueBridge, SSVEPCueRuntime
from test_ssvep_cue_runtime import ASSETS, SOS
from ssvep_shadow import CHANNELS, SSVEPShadow
from unittest.mock import patch


class FreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = 100.
        self.owner = SSVEPCueRuntime(self.root/'cue.jsonl', port=0, clock=lambda: self.now)
        self.bridge = SSVEPCueBridge(self.owner.server.server_port)

    def tearDown(self):
        self.owner.close()
        self.tmp.cleanup()

    def event(self, end=1000, hz=12, **fields):
        scores = [.2, .2, .2, .2]
        scores[(8,10,12,14).index(hz)] = .8
        return dict(dict(source='live', valid=True, state='candidate_only', frequency_hz=hz,
                         updated_monotonic=self.now, input_age_seconds=0.,
                         quality={'hard_bad':False}, scores=scores,
                         window_start_index=end-500, window_end_index_exclusive=end), **fields)

    def start(self, frequencies=None):
        self.owner.observe(self.event())
        result = self.bridge.free_command(dict(action='start',consent=True,
                                               frequencies=frequencies or [8,10,12,14]))
        self.token = result['id']
        self.frequencies = result['frequencies']
        self.began = self.now
        self.bridge.free_command(dict(action='presented',id=self.token,
                                     browser_onset_ms=0,browser_send_ms=0))
        for second in (1,2,3):
            self.now += 1
            self.heartbeat()

    def heartbeat(self, **fields):
        duration = (self.now-self.began)*1000
        return self.owner.free_command(dict(dict(action='heartbeat',id=self.token,
            frame_count=round(duration*.24),duration_ms=duration,max_gap_ms=4.2,
            display_hz={str(f):float(f) for f in self.frequencies}),**fields))

    def windows(self, hz=12, start=1000, count=11, **fields):
        for i in range(count):
            self.now += .2
            self.heartbeat()
            self.owner.observe(self.event(start+50*i, hz, **fields))
        return self.bridge.free_snapshot()

    def test_four_choices_are_decoded_without_target_input(self):
        for hz in (8,10,12,14):
            self.start()
            result = self.windows(hz)
            self.assertEqual(result['result'],hz)
            self.assertTrue(result['accepted'])
            self.assertFalse(result['idle_classifier_validated'])
            self.assertFalse(result['control_enabled'])
            self.bridge.free_command(dict(action='stop',id=self.token))

    def test_polling_and_duplicate_overlap_cannot_confirm(self):
        self.start()
        self.windows(count=1)
        for _ in range(10):
            self.owner.observe(self.event())
            result = self.bridge.free_snapshot()
            self.assertFalse(result['accepted'])
        self.assertFalse(self.windows(start=1050,count=9)['accepted'])
        self.assertTrue(self.windows(start=1500,count=1)['accepted'])

    def test_weak_ambiguous_and_inactive_targets_abstain(self):
        self.start([10,12])
        for scores in ([.1,.2,.3,.1], [.2,.72,.75,.2]):
            self.assertFalse(self.windows(scores=scores)['accepted'])
        self.assertFalse(self.windows(hz=8)['accepted'])

    def test_rejected_windows_record_specific_gates_without_lowering_thresholds(self):
        self.start()
        result=self.windows(scores=[.1,.2,.3,.1],count=1)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['min_score'],.55)
        self.assertIn('score_below_minimum',result['decision']['failures'])
        rows=[json.loads(line) for line in (self.root/'ssvep_free_events.jsonl').read_text().splitlines()]
        rejected=[r for r in rows if r['event']=='window_diagnostic']
        self.assertEqual(len(rejected),1)
        self.assertFalse(rejected[0]['accepted'])
        self.assertEqual(rejected[0]['scores'],[.1,.2,.3,.1])
        self.assertEqual(sum(result['gate_counts'].values()),1)

    def test_switch_requires_new_nonoverlapping_evidence(self):
        self.start()
        self.assertTrue(self.windows()['accepted'])
        self.assertFalse(self.windows(hz=10,start=1550,count=1)['accepted'])
        self.assertEqual(self.windows(hz=10,start=1600,count=10)['result'],10)

    def test_gap_replay_hard_quality_and_stale_revoke(self):
        self.start()
        self.assertTrue(self.windows()['accepted'])
        self.assertFalse(self.windows(start=1650,count=1)['accepted'])
        for fields in ({'source':'replay'}, {'quality':{'hard_bad':True}},
                       {'input_age_seconds':1}, {'updated_monotonic':self.now+10}):
            self.owner.observe(self.event(**fields))
            self.assertIsNone(self.bridge.free_snapshot()['result'])
        self.windows(start=2000)
        self.now += .51
        self.heartbeat()
        self.assertIsNone(self.bridge.free_snapshot()['result'])

    def test_bad_display_and_missing_heartbeat_stop(self):
        self.start()
        self.windows()
        self.heartbeat(display_hz={'8':8.,'10':10.,'12':9.,'14':14.})
        self.assertFalse(self.bridge.free_snapshot()['accepted'])
        self.now += 1.51
        self.assertEqual(self.bridge.free_snapshot()['state'],'stopped')
        with self.assertRaises(ValueError): self.heartbeat()

    def test_start_requires_live_source_and_excludes_cued_session(self):
        with self.assertRaises(ValueError):
            self.bridge.free_command(dict(action='start',consent=True,frequencies=[8,10,12,14]))
        self.start()
        with self.assertRaises(ValueError):
            self.bridge.command(dict(action='start',target_hz=12))
        self.bridge.free_command(dict(action='stop',id=self.token))
        self.owner.observe(self.event())
        self.bridge.command(dict(action='start',target_hz=12))
        with self.assertRaises(ValueError):
            self.bridge.free_command(dict(action='start',consent=True,frequencies=[8,10,12,14]))

    def test_answer_injection_and_audit_failure_are_rejected(self):
        self.owner.observe(self.event())
        with self.assertRaises(ValueError):
            self.bridge.free_command(dict(action='start',consent=True,frequencies=[8,10,12,14],target_hz=12))
        self.start()
        self.owner.free_session.log_path = self.root/'missing'/'free.jsonl'
        self.owner.observe(self.event())
        self.assertFalse(self.bridge.free_snapshot()['accepted'])
        self.assertFalse(self.owner.failed)

    def test_public_route_and_same_origin(self):
        server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(
            self.root/'status',self.root/'telemetry',3,cued_session=self.bridge))
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        base = 'http://127.0.0.1:%d' % server.server_port
        try:
            with urlopen(base+'/ssvep-free') as response:
                self.assertIn(b'four',response.read())
            with urlopen(base+'/api/ssvep-free') as response:
                self.assertEqual(json.load(response)['state'],'idle')
            with self.assertRaises(HTTPError) as failure:
                urlopen(Request(base+'/api/ssvep-free',data=b'{"action":"start"}',
                                headers={'Content-Type':'application/json'}))
            self.assertEqual(failure.exception.code,403)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)

    def test_synthetic_eeg_runs_the_actual_decoder_and_producer(self):
        with patch('ssvep_shadow.time.monotonic',lambda:self.now):
            shadow = SSVEPShadow(ASSETS/'ssvep_causal_protocol.json', SOS, CHANNELS,
                                source='live',status_path=self.root/'shadow.json',
                                event_sink=self.owner.observe)
            time_axis = np.arange(2800)/250
            samples = np.zeros((len(time_axis),8))
            samples[:,6] = 12*np.sin(2*np.pi*12*time_axis)+np.sin(2*np.pi*17*time_axis)
            samples[:,7] = 9*np.sin(2*np.pi*12*time_axis+.3)+np.sin(2*np.pi*19*time_axis)
            for index in range(800):
                self.now = 100+index/250
                shadow.packet(samples[index],index%256,now=self.now)
            result = self.bridge.free_command(dict(action='start',consent=True,frequencies=[8,10,12,14]))
            self.token=result['id'];self.frequencies=result['frequencies'];self.began=self.now
            self.bridge.free_command(dict(action='presented',id=self.token,browser_onset_ms=0,browser_send_ms=0))
            for index in range(800,2800):
                self.now=100+index/250
                if index>800 and index%100==0:self.heartbeat()
                shadow.packet(samples[index],index%256,now=self.now)
            self.assertEqual(self.bridge.free_snapshot()['result'],12)


if __name__=='__main__':
    unittest.main()

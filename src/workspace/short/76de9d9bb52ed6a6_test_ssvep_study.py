"""Synthetic collection fixtures only, not human recognition evidence."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cyton_trial_recorder import read_json
import test_ssvep_recording as fixtures
from ssvep_study import SSVEPStudy
from audit_ssvep_study import audit


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.plan = SSVEPStudy(Path(self.temp.name)/'study', lambda:100.)

    def tearDown(self):
        self.temp.cleanup()

    def test_balanced_frozen_plan_with_distinct_blocks(self):
        state = self.plan.create()
        rows = self.plan.plan['trials']
        self.assertEqual([r['index'] for r in rows], list(range(20)))
        for phase in ('calibration', 'confirmation'):
            labels = [r['requested_hz'] for r in rows if r['phase'] == phase]
            self.assertEqual(Counter(labels), Counter({8:2,10:2,12:2,14:2,0:2}))
        self.assertNotEqual(rows[0]['block_id'], rows[10]['block_id'])
        self.assertFalse(state['decoder_receives_labels'])
        self.assertEqual(self.plan.plan['rest_condition'], 'center_gaze_while_all_four_targets_flicker')
        with self.assertRaises(ValueError):self.plan.create()
        with self.assertRaises(ValueError):self.plan.context('../escape')

    def test_abort_is_saved_and_not_cherry_picked_out(self):
        self.plan.create()
        context = self.plan.context(self.plan.plan['study_id'])
        self.plan.reserve(context, '0000000000000001')
        with self.assertRaises(ValueError):self.plan.context(self.plan.plan['study_id'])
        self.plan.finish({})
        self.assertFalse(self.plan.attempts[0]['collection_complete'])
        self.assertEqual(self.plan.context(self.plan.plan['study_id'])['index'],1)
        with self.assertRaises(ValueError):
            self.plan.reserve(self.plan.context(self.plan.plan['study_id']), '0000000000000001')

    def test_confirmation_cannot_reuse_raw_or_changed_runtime(self):
        self.plan.create()
        with patch.object(self.plan, '_runtime_hashes', return_value={'changed':'yes'}):
            with self.assertRaises(ValueError):self.plan.context(self.plan.plan['study_id'])

    def test_full_plan_closes_with_no_model_fit(self):
        self.plan.create()
        for index in range(20):
            self.plan.reserve(self.plan.context(self.plan.plan['study_id']), f'{index:016x}')
            self.plan.attach('session')
            self.plan.presented()
            self.plan.clock=lambda:110.
            self.plan.stopped('user_or_display_stopped')
            self.plan.finish(dict(state='complete',trial_id=f'{index:016x}',samples=2500))
            self.plan.clock=lambda:100.
        state = self.plan.snapshot()
        self.assertEqual(state['state'],'complete')
        self.assertFalse(state['thresholds_fitted'])
        self.assertTrue(all(a['collection_complete'] for a in self.plan.attempts))
        self.assertEqual(len({a['raw_recording_id'] for a in self.plan.attempts}),20)

    def test_offline_audit_preserves_missing_capture_and_rejects_relabeling(self):
        self.plan.create()
        self.plan.reserve(self.plan.context(self.plan.plan['study_id']), '0000000000000001')
        self.plan.finish({})
        events=Path(self.temp.name)/'events';events.write_text('')
        study=self.plan.directory/(self.plan.plan['study_id']+'.json')
        result=audit(study,Path(self.temp.name)/'raw',events)
        self.assertFalse(result['complete_collection'])
        self.assertFalse(result['attempts'][0]['eligible_for_future_analysis'])
        data=json.loads(study.read_text());data['attempts'][0]['requested_hz']=99
        study.write_text(json.dumps(data))
        with self.assertRaises(ValueError):audit(study,Path(self.temp.name)/'raw',events)


class FreeRecordingTests(unittest.TestCase):
    setUp = fixtures.RecordingTests.setUp
    tearDown = fixtures.RecordingTests.tearDown
    fresh = fixtures.RecordingTests.fresh
    finish_pending = fixtures.RecordingTests.finish_pending

    def prepare(self, study=False):
        request = dict(action='record_start', consent=True, frequencies=[8,10,12,14])
        if study:
            state = self.owner.free_command(dict(action='study_create',consent=True))
            request['study_id'] = state['study']['id']
        self.owner.free_command(request)
        self.recorder.poll(self.counters)
        for n in range(250):
            self.recorder.append([n]*8,n%256,False,False,stream_index=n,received_at=self.now)
        self.now += 1.1
        self.recorder.poll(self.counters)
        self.fresh()
        self.assertEqual(self.owner.free_snapshot()['recording_control']['state'],'ready')
        return self.recorder.active['directory']

    def start(self):
        return self.owner.free_command(dict(action='start',consent=True,
            frequencies=[8,10,12,14],require_raw_recording=True))

    def test_free_first_ack_is_not_ready_and_forged_context_fails(self):
        with self.assertRaises(ValueError):
            self.owner.free_command(dict(action='start',consent=True,frequencies=[8,10,12,14],
                require_raw_recording=True,raw_recording={'trial_id':'fake'}))
        self.owner.free_command(dict(action='record_start',consent=True,frequencies=[8,10,12,14]))
        self.recorder.poll(self.counters)
        self.owner.free_snapshot()
        with self.assertRaises(ValueError):self.start()

    def test_recording_link_boot_identity_and_stop_ack(self):
        path=self.prepare()
        trial=self.start()
        rows=[json.loads(line) for line in (self.root/'ssvep_free_events.jsonl').read_text().splitlines()]
        self.assertEqual(rows[0]['raw_recording_id'],path.name)
        self.assertEqual(rows[0]['board_boot_id'],read_json(path/'metadata.json')['board_boot_id'])
        self.assertEqual(read_json(path/'metadata.json')['cue_log_path'],str(self.root/'ssvep_free_events.jsonl'))
        self.assertFalse(trial['raw_capture_completeness_verified'])
        self.owner.free_command(dict(action='stop',id=trial['id']))
        self.recorder.poll(self.counters)
        self.now+=.3;self.recorder.poll(self.counters)
        self.assertEqual(self.owner.free_snapshot()['recording_control']['state'],'complete')

    def test_cross_page_arming_and_other_tasks_are_protected(self):
        self.owner.free_command(dict(action='record_start',consent=True,frequencies=[8,10,12,14]))
        with self.assertRaises(ValueError):
            self.owner.command(dict(action='start',target_hz=12))
        with self.assertRaises(ValueError):
            self.owner.command(dict(action='record_start',target_hz=12,consent=True))
        self.owner.free_command(dict(action='record_cancel'))
        self.recorder.poll(self.counters);self.owner.free_snapshot()
        self.now+=.3;self.recorder.poll(self.counters);self.owner.free_snapshot()
        self.now+=.3
        self.fresh()
        fixtures.RecordingTests.prepare(self)
        with self.assertRaises(ValueError):
            self.owner.free_command(dict(action='start',consent=True,frequencies=[8,10,12,14]))

    def test_free_cancel_before_ack_closes_late_start(self):
        self.owner.free_command(dict(action='record_start',consent=True,frequencies=[8,10,12,14]))
        self.owner.free_command(dict(action='record_cancel'))
        self.recorder.poll(self.counters);self.owner.free_snapshot()
        self.now+=.3;self.recorder.poll(self.counters)
        self.assertEqual(self.owner.free_snapshot()['recording_control']['state'],'complete')

    def test_plan_label_does_not_decide_frequency_and_abort_remains_saved(self):
        path=self.prepare(study=True)
        label=self.owner.study.pending['requested_hz']
        hz=10 if label!=10 else 12
        trial=self.start()
        self.owner.free_command(dict(action='presented',id=trial['id'],browser_onset_ms=0,browser_send_ms=0))
        onset=self.now
        for n in range(25):
            self.now+=.2
            duration=(self.now-onset)*1000
            self.owner.free_command(dict(action='heartbeat',id=trial['id'],frame_count=round(duration*.24),
                duration_ms=duration,max_gap_ms=4.2,display_hz={str(f):float(f) for f in (8,10,12,14)}))
            self.recorder.publish('recording')
            scores=[.1,.1,.1,.1];scores[(8,10,12,14).index(hz)]=.8
            end=1000+n*50
            self.owner.observe(dict(source='live',state='candidate_only',valid=True,frequency_hz=hz,
                updated_monotonic=self.now,input_age_seconds=0.,quality={'hard_bad':False},
                scores=scores,window_start_index=end-500,window_end_index_exclusive=end))
        self.assertEqual(self.owner.free_snapshot()['result'],hz)
        self.assertNotEqual(hz,label)
        with self.assertRaises(ValueError):
            self.owner.free_command(dict(action='start',consent=True,frequencies=[8,10,12,14],target_hz=hz))
        self.owner.free_command(dict(action='stop',id=trial['id']))
        self.now+=.3;self.recorder.poll(self.counters);self.owner.free_snapshot()
        attempt=self.owner.study.attempts[0]
        self.assertFalse(attempt['collection_complete'])
        self.assertEqual(attempt['raw_recording_id'],path.name)
        rows=[json.loads(line) for line in (self.root/'ssvep_free_events.jsonl').read_text().splitlines()]
        self.assertTrue(all('requested_hz' not in r and 'target_hz' not in r for r in rows))
        report=audit(self.owner.study.directory/(self.owner.study.plan['study_id']+'.json'),
                     self.root/'recordings',self.root/'ssvep_free_events.jsonl')
        self.assertTrue(report['attempts'][0]['integrity'])
        self.assertFalse(report['attempts'][0]['eligible_for_future_analysis'])

    def test_lost_raw_withdraws_and_plan_creation_never_starts_capture(self):
        self.owner.free_command(dict(action='study_create',consent=True))
        self.assertIsNone(self.recorder.active)
        self.assertFalse((self.root/'command.json').exists())
        path=self.prepare()
        trial=self.start()
        self.recorder.finish('duration_limit',self.counters)
        view=self.owner.free_snapshot()
        self.assertEqual(view['state'],'stopped')
        self.assertEqual(view['reason'],'raw_recording_unavailable')
        self.assertIsNone(view['result'])


if __name__=='__main__':unittest.main()

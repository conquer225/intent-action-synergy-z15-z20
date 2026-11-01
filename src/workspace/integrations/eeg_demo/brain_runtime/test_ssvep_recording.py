"""No human stimulation: exercise the real recorder's command and ACK lifecycle."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cyton_trial_recorder import TrialRecorder, atomic_json, read_json
from ssvep_cue_runtime import SSVEPCueRuntime


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = 100.
        self.time_patch = patch('cyton_trial_recorder.time.monotonic',lambda:self.now)
        self.time_patch.start()
        self.counters = dict(packets_seen=1)
        self.recorder = TrialRecorder(['F3','F4','C3','C4','T7','T8','O1','O2'],.02,
            self.root/'command.json',self.root/'status.json',self.root/'recordings')
        self.owner = SSVEPCueRuntime(self.root/'cue.jsonl',port=0,clock=lambda:self.now,
            record_status_path=self.root/'status.json',record_command_path=self.root/'command.json')
        self.fresh()

    def fresh(self):
        self.owner.observe(dict(source='live',state='candidate_only',valid=True,
            updated_monotonic=self.now,input_age_seconds=0.,frequency_hz=10,
            quality={'hard_bad':False}))

    def tearDown(self):
        self.owner.close()
        self.recorder.close(self.counters)
        self.time_patch.stop()
        self.tmp.cleanup()

    def prepare(self):
        requested = self.owner.command(dict(action='record_start',target_hz=10,consent=True))
        self.assertEqual(requested['state'],'idle')
        self.assertEqual(requested['recording_control']['state'],'starting')
        self.recorder.poll(self.counters)
        for n in range(250):
            self.recorder.append([n]*8,n%256,False,False,stream_index=n,received_at=self.now)
        self.now += 1.1
        self.recorder.poll(self.counters)
        self.fresh()
        self.assertEqual(self.owner.snapshot()['recording_control']['state'],'ready')
        return self.recorder.active['directory']

    def finish_pending(self):
        self.now += .3
        self.recorder.poll(self.counters)
        return self.owner.snapshot()

    def test_checked_flow_records_real_bytes_links_cue_and_closes_on_stop(self):
        path = self.prepare()
        trial = self.owner.command(dict(action='start',target_hz=10,require_raw_recording=True))
        self.assertEqual(trial['raw_recording']['samples'],250)
        self.assertEqual((path/'samples_i32le.bin').stat().st_size,8000)
        row=json.loads((self.root/'cue.jsonl').read_text().splitlines()[0])
        self.assertEqual(row['raw_recording_id'],path.name)
        self.assertFalse(row['raw_capture_completeness_verified'])
        self.owner.command(dict(action='stop',id=trial['id']))
        self.assertEqual(read_json(self.root/'command.json')['action'],'stop')
        self.assertEqual(self.finish_pending()['recording_control']['state'],'complete')
        metadata=read_json(path/'metadata.json')
        self.assertEqual(metadata['state'],'complete')
        self.assertEqual(metadata['channel_map'],['F3','F4','C3','C4','T7','T8','O1','O2'])

    def test_first_ack_alone_is_not_enough_to_start_flashing(self):
        self.owner.command(dict(action='record_start',target_hz=12,consent=True))
        self.recorder.poll(self.counters)
        self.owner.snapshot()
        with self.assertRaisesRegex(ValueError,'首批样本'):
            self.owner.command(dict(action='start',target_hz=12,require_raw_recording=True))
        self.assertEqual(self.owner.session.snapshot()['state'],'idle')

    def test_cancel_before_ack_does_not_orphan_late_recording(self):
        self.owner.command(dict(action='record_start',target_hz=10,consent=True))
        self.owner.command(dict(action='record_cancel'))
        self.recorder.poll(self.counters)
        self.owner.snapshot()
        self.assertEqual(read_json(self.root/'command.json')['action'],'stop')
        self.assertEqual(self.finish_pending()['recording_control']['state'],'complete')

    def test_external_recording_is_linked_but_never_stopped(self):
        self.prepare()
        self.owner.recording_control.owned=None
        command_id=read_json(self.root/'command.json')['id']
        result=self.owner.command(dict(action='record_start',target_hz=10,consent=True))
        self.assertEqual(result['recording_control']['state'],'external')
        trial=self.owner.command(dict(action='start',target_hz=10,require_raw_recording=True))
        self.owner.command(dict(action='stop',id=trial['id']))
        self.owner.command(dict(action='record_cancel'))
        self.assertEqual(read_json(self.root/'command.json')['id'],command_id)
        self.assertIsNotNone(self.recorder.active)

    def test_other_task_pending_command_and_missing_consent_refuse(self):
        with self.assertRaises(ValueError):
            self.owner.command(dict(action='record_start',target_hz=10))
        atomic_json(self.root/'command.json',dict(id='pending'))
        with self.assertRaisesRegex(ValueError,'上一条'):
            self.owner.command(dict(action='record_start',target_hz=10,consent=True))
        atomic_json(self.root/'status.json',dict(state='recording',task='emotion',last_command='pending'))
        with self.assertRaisesRegex(ValueError,'其他'):
            self.owner.command(dict(action='record_start',target_hz=10,consent=True))

    def test_browser_lost_before_trial_closes_after_prepare_timeout(self):
        self.prepare()
        self.now += 12.1
        self.owner.snapshot()
        self.assertEqual(read_json(self.root/'command.json')['action'],'stop')
        self.assertEqual(self.finish_pending()['recording_control']['state'],'complete')

    def test_worker_crash_cannot_leave_recording_longer_than_45_seconds(self):
        path=self.prepare()
        self.now += 45.1
        self.recorder.poll(self.counters)
        self.assertIsNone(self.recorder.active)
        self.assertEqual(read_json(path/'metadata.json')['state'],'duration_limit')

    def test_bad_duration_does_not_create_raw_directory(self):
        with self.assertRaises(ValueError):
            self.recorder.start(dict(trial_id='0123456789abcdef',task='ssvep',
                phase='ssvep_diagnostic',condition='ssvep_cued_diagnostic',max_seconds=0),self.counters)
        self.assertFalse((self.root/'recordings').exists())

    def test_hdmi_raw_ack_links_events_and_stops_without_optical_claim(self):
        request=dict(action='record_start',consent=True,frequencies=[8,10,12,14])
        first=self.owner.hdmi_command(request)
        self.assertEqual(first['recording_control']['state'],'starting')
        self.recorder.poll(self.counters)
        self.owner.hdmi_snapshot()
        start=dict(action='start',consent=True,page_id=1,frequencies=[8,10,12,14],require_raw_recording=True)
        with self.assertRaisesRegex(ValueError,'尚未就绪'):self.owner.hdmi_command(start)
        for n in range(250):
            self.recorder.append([n]*8,n%256,False,False,stream_index=n,received_at=self.now)
        self.now+=1.1;self.recorder.poll(self.counters);self.fresh()
        path=self.recorder.active['directory']
        self.assertEqual(self.owner.hdmi_snapshot()['recording_control']['state'],'ready')
        trial=self.owner.hdmi_command(start)
        self.assertEqual(trial['raw_recording_id'],path.name)
        # Browser polling cannot cancel a capture owned by the HDMI session.
        self.owner.snapshot();self.owner.free_snapshot()
        self.assertEqual(read_json(self.root/'command.json')['action'],'start')
        with self.assertRaises(ValueError):self.owner.command(dict(action='record_start',consent=True,target_hz=10))
        self.owner.hdmi_command(dict(action='stop',id=trial['id']))
        self.now+=.3;self.recorder.poll(self.counters)
        self.assertEqual(self.owner.hdmi_snapshot()['recording_control']['state'],'complete')
        metadata=read_json(path/'metadata.json')
        self.assertEqual(metadata['condition_requested'],'ssvep_hdmi_diagnostic')
        self.assertFalse(metadata['protocol']['optical_onset_measured'])
        self.assertTrue(metadata['cue_log_path'].endswith('ssvep_hdmi_events.jsonl'))
        event=json.loads((self.root/'ssvep_hdmi_events.jsonl').read_text().splitlines()[0])
        self.assertEqual(event['raw_recording_id'],path.name)

    def test_hdmi_cancel_before_ack_closes_late_capture(self):
        self.owner.hdmi_command(dict(action='record_start',consent=True,frequencies=[8,10,12,14]))
        self.owner.hdmi_command(dict(action='record_cancel'))
        self.recorder.poll(self.counters);self.owner.hdmi_snapshot()
        self.assertEqual(read_json(self.root/'command.json')['action'],'stop')


if __name__=='__main__':unittest.main()

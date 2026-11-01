"""Recorded-load evidence must retain withdrawals, missing windows and buffering."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compute_relief


class SummaryTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        for name in ('profile13','profile14'):
            (self.root/name).mkdir()
        self.prediction=dict(window=1,packets_seen=50,state='NORMAL',valid=True,
            level='NORMAL',score=.3,calibration_current=15,calibration_retained=True,
            emotion=dict(state='prediction',valid=True,class_id=0))
        self.closed=dict(window=1,packets_seen=100,state='INVALID',valid=False,
            reason='SERVICE_STOPPED_OR_STREAM_TIMEOUT',calibration_current=15,
            calibration_retained=True,emotion=dict(valid=False,state='stream_interrupted'))
        self.report=dict(requested_seconds=156,packets_consumed=100,packets_expected=100,
            monitor_errors=[],error=None,remaining_children=[],packet_input_age_p95_ms=100,
            packet_input_age_max_ms=200)
        self.display=[dict(frame=i*20,updated_monotonic=10+i,monotonic=10+i,
            session='same',state='playing',page='video',physical=False,stimulus=False) for i in range(3)]

    def summarize(self,results,display=None):
        def write(path,value):
            path.write_text(json.dumps(value))
        folder=self.root/'profile14'
        write(folder/'report.json',self.report)
        write(folder/'primary_results.json',[dict(result=r) for r in results])
        write(self.root/'profile13/primary_results.json',[dict(result=self.prediction),dict(result=self.closed)])
        (folder/'monitor.jsonl').write_text(json.dumps(dict(runtime=dict(primary_stream_resets=1)))+'\n')
        write(self.root/'display-observations-actual14.json',self.display if display is None else display)
        with patch.object(compute_relief,'OUT',self.root),redirect_stdout(io.StringIO()):
            compute_relief.summarize(14)
        return json.loads((folder/'verification-summary.json').read_text())

    def test_backlog_withdrawal_is_not_a_model_difference(self):
        backlog=dict(self.prediction,state='INVALID',valid=False,reason='PROCESSING_BACKLOG',
                     emotion=dict(valid=False,state='stream_interrupted'))
        result=self.summarize([self.prediction,backlog,self.closed])
        self.assertEqual(result['backlog_invalidations'],1)
        self.assertEqual(result['model_reference']['differences'],[])
        self.assertTrue(result['results_withdrawn_at_end'])
        self.assertTrue(result['calibration_retained_after_completion'])

    def test_buffering_fails_even_when_counter_average_is_twenty(self):
        display=[dict(row) for row in self.display]
        display[1]['state']='buffering'
        result=self.summarize([self.prediction,self.closed],display)
        self.assertEqual(result['display_including_buffering']['weighted_fps'],20)
        self.assertTrue(result['display_session_scope_unchanged'])
        self.assertEqual(result['buffering_observations'],1)
        self.assertFalse(result['published_intervals_16fps_met'])

    def test_completed_calibration_cannot_drop_to_zero(self):
        result=self.summarize([self.prediction,dict(self.closed,calibration_current=0,calibration_retained=False)])
        self.assertFalse(result['calibration_retained_after_completion'])

    def test_real_model_difference_and_missing_window_remain_visible(self):
        changed=dict(self.prediction,score=.8)
        moved=dict(self.closed,window=2)
        result=self.summarize([changed,moved])
        self.assertEqual(result['model_reference']['differences'][0]['fields'],['score'])
        self.assertEqual(result['model_reference']['reference_only'],[[1,100]])
        self.assertEqual(result['model_reference']['candidate_only'],[[2,100]])

    def test_valid_final_prediction_is_not_successful_withdrawal(self):
        result=self.summarize([self.prediction])
        self.assertFalse(result['results_withdrawn_at_end'])

    def test_fatigue_numeric_difference_and_worker_backlog_are_not_hidden(self):
        changed=dict(self.prediction,perclos=.8)
        backlog=dict(self.closed,reason='PRIMARY_WORKER_BACKLOG')
        result=self.summarize([changed,backlog,self.closed])
        self.assertEqual(result['model_reference']['differences'][0]['fields'],['perclos'])
        self.assertEqual(result['backlog_invalidations'],1)


if __name__=='__main__':
    unittest.main()

import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from validation import Validation, assess

class ValidationTests(unittest.TestCase):
    def result(self):
        return {'validation':True,'unchanged':True,'max_gap_ms':25,
                'points':[{'samples':480,'valid':470,'correct':465} for _ in range(9)]}

    def test_each_hold_must_pass_not_just_total(self):
        event=self.result();self.assertTrue(assess(event)[0])
        event['points'][4]['correct']=20
        self.assertFalse(assess(event)[0])
        self.assertFalse(assess(event,baseline=True)[0])

    def test_accepted_baseline_does_not_claim_strict_success(self):
        event=self.result();event['points'][5]['valid']=350;event['points'][5]['correct']=350
        self.assertFalse(assess(event)[0]);self.assertTrue(assess(event,baseline=True)[0])
        state=Validation();state.phase='vprocessing';state.finish(event)
        self.assertEqual(state.phase,'usable')

    def test_model_gaps_and_absent_samples_fail(self):
        for change in ({'unchanged':False},{'max_gap_ms':float('nan')},{'max_gap_ms':300},{'points':[]}):
            event=self.result();event.update(change);self.assertFalse(assess(event)[0])
        event=self.result();event['points'][0]={'samples':0,'valid':0,'correct':0}
        self.assertFalse(assess(event)[0])

    def test_invalid_and_stale_gaze_cannot_display_a_direction(self):
        state=Validation();state.phase='vcollect';state.started=0
        state.update_gaze({'valid':True,'x':.2,'y':.5},1)
        self.assertIn('左',state.tick(1).detail)
        self.assertIn('无有效',state.tick(1.4).detail)
        for x in (None,True,float('nan'),-1,1.1):
            state.update_gaze({'valid':True,'x':x,'y':.5},2)
            self.assertIn('无有效',state.tick(2).detail)

    def test_no_completion_from_time_or_partial_result(self):
        state=Validation();state.start(0)
        self.assertEqual(state.tick(5).phase,'vsettle')
        self.assertEqual(state.tick(7).phase,'vcollect')
        self.assertEqual(state.tick(15).phase,'vsettle')
        state.finish(self.result());self.assertEqual(state.phase,'vsettle')
        state.phase='vprocessing';state.started=20
        self.assertEqual(state.tick(32).phase,'failed')

if __name__=='__main__':unittest.main()

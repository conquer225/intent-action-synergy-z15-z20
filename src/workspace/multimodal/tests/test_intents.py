import unittest
from intent_one.intents import BrainSelection

class IntentTests(unittest.TestCase):
    def test_two_complete_windows_and_measured_display_are_required(self):
        gate=BrainSelection();gate.start(7,0)
        display={'epoch':7,'active':True,'refresh_hz':60,'rates':[8,10,12,14],'seconds':2,'max_gap_ms':17}
        row=dict(source='live',valid=True,state='candidate_only',quality={'hard_bad':False},input_age_seconds=.1,
                 updated_monotonic=3,window_start_index=250,window_end_index_exclusive=750,scores=[.8,.1,.2,.3],frequency_hz=8)
        self.assertIsNone(gate.observe(row,3,display))
        for n in range(1,10):
            row.update(updated_monotonic=3+.2*n,window_start_index=250+50*n,window_end_index_exclusive=750+50*n)
            self.assertIsNone(gate.observe(row,3+.2*n,display))
        row.update(updated_monotonic=5,window_start_index=750,window_end_index_exclusive=1250)
        self.assertEqual(gate.observe(row,5,display),0)
        self.assertIsNone(gate.observe(row,5.1,display))
        gate.start(8,6);self.assertIsNone(gate.observe(row,6,display))
    def test_invalid_replay_ambiguous_and_stale_never_select(self):
        g=BrainSelection();g.start(1,0)
        self.assertIsNone(g.observe({'source':'replay'},5,{}))
        self.assertIsNone(g.observe({'source':'live','valid':False},5,{}))

if __name__=='__main__': unittest.main()

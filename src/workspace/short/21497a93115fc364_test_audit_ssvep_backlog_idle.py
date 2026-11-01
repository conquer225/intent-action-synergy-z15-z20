"""Guard/rejection diagnostics must preserve discontinuities and abstentions."""
import unittest

from audit_ssvep_backlog_idle import fresh_after_guard, summarize_rule


class SavedDiagnosticTests(unittest.TestCase):
    def row(self, end=500, hz=10., eligible=True):
        return dict(window_end_index_exclusive=end, frequency_hz=hz, _eligible=eligible)

    def test_rejection_breaks_streak(self):
        rows=[self.row(500),self.row(550),self.row(600),self.row(650)]
        result=summarize_rule(rows,[True,True,False,True],10.)
        self.assertEqual(result['longest_consecutive_runs'],{'10.0':2})
        self.assertFalse(result['any_three_target_run'])

    def test_missing_hop_breaks_streak(self):
        rows=[self.row(500),self.row(550),self.row(650)]
        self.assertFalse(summarize_rule(rows,[True]*3,10.)['any_three_target_run'])

    def test_rest_run_is_not_accuracy(self):
        rows=[self.row(500),self.row(550),self.row(600)]
        result=summarize_rule(rows,[True]*3,0.)
        self.assertTrue(result['any_three_same_frequency_run'])
        self.assertIsNone(result['any_three_target_run'])
        self.assertFalse(result['independent_accuracy_claimed'])

    def test_stale_and_guard_excluded(self):
        row=dict(state='candidate_only',valid=True,stale=False,source='live',
                 input_age_seconds=.1,board_monotonic_s=4.,
                 shadow_updated_monotonic_s=4.,quality={'hard_bad':False})
        self.assertTrue(fresh_after_guard(row,1.))
        self.assertFalse(fresh_after_guard(row,2.))
        self.assertFalse(fresh_after_guard(dict(row,input_age_seconds=.6),1.))
        self.assertFalse(fresh_after_guard(dict(row,state='no_data',valid=False),1.))


if __name__=='__main__':
    unittest.main()

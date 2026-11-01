import unittest

from compare_seed_event_audits import equivalent, equivalent_gap


class EventComparisonTest(unittest.TestCase):
    def test_scores_compare_numerically(self):
        self.assertTrue(equivalent({'scores': [.1, .2]},
                                   {'scores': [.10000000001, .2]}))
        self.assertFalse(equivalent({'scores': [.1, .2]},
                                    {'scores': [.1, .3]}))

    def test_gap_timing_tolerance_keeps_policy_check(self):
        reference = {'baseline_retained': True, 'reason': 'counter_ok', 'seconds': 1.04}
        self.assertTrue(equivalent_gap(reference, {**reference, 'seconds': 1.05}))
        self.assertFalse(equivalent_gap(reference, {**reference, 'seconds': 1.5}))
        self.assertFalse(equivalent_gap(reference, {**reference, 'baseline_retained': False}))


if __name__ == '__main__':
    unittest.main()

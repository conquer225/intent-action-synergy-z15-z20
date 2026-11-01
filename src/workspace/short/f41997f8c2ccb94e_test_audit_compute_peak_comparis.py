import unittest

from audit_compute_peak_comparison import performance_gates, primary_parity


class AuditTest(unittest.TestCase):
    def test_no_average_only_acceptance(self):
        base = dict(feature_max_ms=100, input_age_p95_ms=300, input_age_max_ms=500, total_cpu_seconds=100)
        candidate = dict(feature_max_ms=40, input_age_p95_ms=200, input_age_max_ms=501, total_cpu_seconds=101)
        plan = dict(min_feature_max_speedup_fraction=.5, min_age_p95_improvement_fraction=.15,
                    max_cpu_total_increase_fraction=.1)
        result = performance_gates(base, candidate, plan)
        self.assertFalse(result['passed'])
        self.assertFalse(result['gates']['input_age_max_not_worse'])

    def test_primary_mismatch_and_missing_publication(self):
        base = [dict(result=dict(emotion=dict(pair_scores=[1.0], class_id=0), valid=True), calibrated=True)]
        self.assertTrue(primary_parity(base, base)['passed'])
        self.assertFalse(primary_parity(base, [])['passed'])
        changed = [dict(result=dict(emotion=dict(pair_scores=[1.0], class_id=1), valid=True), calibrated=True)]
        self.assertFalse(primary_parity(base, changed)['passed'])


if __name__ == '__main__':
    unittest.main()

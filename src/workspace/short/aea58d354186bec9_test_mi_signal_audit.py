import unittest

import numpy as np
from mi_signal_audit import filter_response, laterality, response_at


class SignalAuditTests(unittest.TestCase):
    def setUp(self):
        self.baseline = np.ones((4, 7, 8))
        self.task = self.baseline.copy()
        self.labels = np.array([0, 1, 0, 1])
        self.people = np.array([1, 1, 2, 2])

    def test_contralateral_reduction_has_positive_contrast(self):
        self.task[self.labels == 0, :, 3] = .5
        self.task[self.labels == 1, :, 2] = .5
        for row in laterality(self.baseline, self.task, self.labels, self.people, [1, 2]):
            self.assertEqual(row['positive_person_count'], 2)
            self.assertAlmostEqual(row['mean_person_contrast'], 2 * np.log(2))

    def test_zero_contrast(self):
        rows = laterality(self.baseline, self.task, self.labels, self.people, [1, 2])
        self.assertEqual(rows[0]['zero_person_count'], 2)

    def test_missing_people_and_labels_rejected(self):
        with self.assertRaises(ValueError):
            laterality(self.baseline, self.task, self.labels, self.people, [1, 3])
        with self.assertRaises(ValueError):
            laterality(self.baseline, self.task, np.zeros(4), self.people, [1, 2])

    def test_nonfinite_and_negative_not_dropped(self):
        for invalid in (np.nan, -1):
            self.task[0, 0, 0] = invalid
            with self.assertRaises(ValueError):
                laterality(self.baseline, self.task, self.labels, self.people, [1, 2])

    def test_common_gain_cancels(self):
        self.task[0, :, 2] = .5
        expected = laterality(self.baseline, self.task, self.labels, self.people, [1, 2])
        actual = laterality(17 * self.baseline, 17 * self.task, self.labels, self.people, [1, 2])
        self.assertEqual(expected, actual)

    def test_group_delay_unit_and_sign(self):
        pure_delay = np.array([[0, 1, 0, 1, 0, 0]], dtype=float)
        gain, delay = response_at(pure_delay, 10)
        self.assertAlmostEqual(gain, 1)
        self.assertAlmostEqual(delay, 1 / 250, places=10)

    def test_filter_audit_is_finite_and_retains_fir_delay(self):
        for point in filter_response()['points']:
            self.assertTrue(np.isfinite([point['gain_db'], point['total_group_delay_s']]).all())
            self.assertAlmostEqual(point['resampler_group_delay_s'], .04)
            self.assertGreater(point['total_group_delay_s'], .04)


if __name__ == '__main__':
    unittest.main()

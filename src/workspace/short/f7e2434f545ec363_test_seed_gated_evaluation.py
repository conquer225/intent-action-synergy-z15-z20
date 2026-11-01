import unittest

import numpy as np

from .seed_gated_evaluation import metrics


class CoverageMetricsTests(unittest.TestCase):
    def test_no_output_is_not_perfect_accuracy(self):
        result = metrics(np.zeros((3, 3)), [100, 100, 100])
        self.assertIsNone(result['accepted_balanced_accuracy'])
        self.assertIsNone(result['accepted_accuracy'])
        self.assertEqual(result['coverage'], 0)
        self.assertEqual(result['balanced_correct_output_yield'], 0)

    def test_abstention_remains_in_denominator(self):
        result = metrics(np.eye(3)*5, [120, 120, 120])
        self.assertEqual(result['accepted_balanced_accuracy'], 1)
        self.assertEqual(result['coverage'], .5)
        self.assertEqual(result['balanced_correct_output_yield'], .5)

    def test_missing_class_cannot_be_dropped(self):
        result = metrics(np.diag([5, 0, 5]), [120, 120, 120])
        self.assertIsNone(result['accepted_balanced_accuracy'])
        self.assertEqual(result['accepted_accuracy'], 1)
        self.assertAlmostEqual(result['coverage'], 1/3)


if __name__ == '__main__':
    unittest.main()

import json
from pathlib import Path
import unittest
import numpy as np


class ReferenceTests(unittest.TestCase):
    def test_linear_mlp_float_identity_for_positive_and_negative_scores(self):
        from z20_compute.reference_models import linear_parameters
        weight = np.zeros((3, 180)); weight[:, :2] = [[2, -3], [-4, 1], [.5, 2]]
        bias = np.array([-3., 1., 2.])
        w1, b1, w2, b2 = linear_parameters(weight, bias)
        for a, b in ((2., -1.), (-4., 3.), (0., 0.)):
            values = np.zeros(180); values[:2] = [a, b]
            np.testing.assert_allclose(w2 @ np.maximum(w1 @ values+b1, 0)+b2,
                                       weight @ values+bias, rtol=0, atol=1e-12)

    def test_fatigue_teacher_preserves_thresholds_and_tree_decisions(self):
        from z20_compute.reference_models import fatigue_scores, fatigue_labels
        model = dict(baseline_prediction=.2, thresholds=[.35, .7], trees=[
            [[0., 0, 1., 1, 2, False, False], [.15, 0, 0, 0, 0, False, True],
             [.5, 0, 0, 0, 0, False, True]]])
        x = np.zeros((3, 20)); x[:, 0] = [0., 1., 2.]
        np.testing.assert_allclose(fatigue_scores(model, x), [.35, .35, .7])
        np.testing.assert_array_equal(fatigue_labels(model, x), [1, 1, 2])


if __name__ == '__main__': unittest.main()

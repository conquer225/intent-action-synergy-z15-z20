import unittest
from mi_residual_diagnostic import (fit_residual, corrected_probability, class1_probability,
    select_candidate, fit_validation_indices, read, PROTOCOL)
from sklearn.linear_model import Ridge
import numpy as np


class ResidualTests(unittest.TestCase):
    def test_dual_matches_svd_all_alphas(self):
        rng = np.random.default_rng(42)
        z, y, base = rng.normal(size=(80, 240)), np.arange(80) % 2, rng.uniform(size=80)
        for alpha in read(PROTOCOL)['alphas_in_tie_preference_order']:
            w, b = fit_residual(z, y, base, alpha)
            reference = Ridge(alpha=80 * alpha, solver='svd').fit(z, y-base)
            np.testing.assert_allclose(w, reference.coef_, rtol=1e-9, atol=1e-9)
            np.testing.assert_allclose(b, reference.intercept_, rtol=1e-9, atol=1e-9)

    def test_constant_columns_do_not_fail(self):
        w, b = fit_residual(np.ones((80, 240)), np.arange(80)%2, np.full(80, .3), .1)
        np.testing.assert_array_equal(w, 0)
        self.assertAlmostEqual(b, .2)

    def test_identity_exact_and_tie_class0(self):
        base = np.array([0., .5, 1.])
        np.testing.assert_array_equal(corrected_probability(base, [10, -1, -10], 0, .15), base)
        np.testing.assert_array_equal(base > .5, [False, False, True])

    def test_bounded_change_and_strong_no_flip(self):
        base = np.linspace(0, 1, 101)
        result = corrected_probability(base, np.where(base > .5, -100, 100), 1., .15)
        self.assertLessEqual(np.max(np.abs(result-base)), .15 + 1e-14)
        safe = np.abs(base-.5) > .15 + 1e-14
        np.testing.assert_array_equal(result[safe] > .5, base[safe] > .5)

    def test_free_ablation_can_override_strong_source(self):
        np.testing.assert_array_equal(corrected_probability([.99,.01], [-2,2], 1., None), [0,1])

    def test_softmax_stable(self):
        logits = np.array([[0,1000],[0,-1000],[1000,1000],[1,2]], dtype=float)
        np.testing.assert_allclose(class1_probability(logits), [1,0,.5,1/(1+np.exp(-1))])

    def test_nonfinite_or_wrong_shape_rejected(self):
        for logits in (np.array([1,2]), np.array([[0,np.inf]])):
            with self.assertRaises(ValueError): class1_probability(logits)
        for base, residual, strength, cap in (([.2],[np.nan],1,.15),([2.],[1.],1,.15),([.2],[1.],2,.15),([.2],[1.],1,0)):
            with self.assertRaises(ValueError): corrected_probability(base,residual,strength,cap)

    def test_nonpositive_ridge_or_wrong_labels_rejected(self):
        for labels, alpha in ((np.arange(80)%2,0),(np.zeros(80),.1)):
            with self.assertRaises(ValueError): fit_residual(np.ones((80,2)),labels,np.full(80,.5),alpha)

    def test_validation_ties_favor_identity_and_13_budget(self):
        p = read(PROTOCOL)
        best, history = select_candidate(p,np.zeros((4,240)),np.zeros(4),np.ones((40,240)),np.full(40,.5),np.arange(40)%2,.15)
        self.assertEqual(best,0); self.assertEqual(len(history),13)
        self.assertEqual(history[1]['strength'],.25); self.assertEqual(history[1]['alpha'],10)
        self.assertEqual(history[-1]['strength'],1); self.assertEqual(history[-1]['alpha'],.01)

    def test_80_40_test_indices_strict(self):
        subjects, order = np.ones(200,dtype=int), np.arange(200)
        case = {'person':1,'personal_fit':list(range(80)),'personal_validation':list(range(80,120)),'test':list(range(120,200))}
        fit,val = fit_validation_indices(case,subjects,order)
        self.assertEqual((len(fit),len(val)),(80,40))
        case['personal_fit'][-1] = 120
        with self.assertRaises(AssertionError): fit_validation_indices(case,subjects,order)

    def test_locked_montage_people_and_seeds(self):
        p = read(PROTOCOL)
        self.assertEqual(p['channels'],['F3','F4','C3','C4','T7','T8','O1','O2'])
        self.assertEqual(len(set(p['participants'])),30); self.assertEqual(p['seeds'],[42,43,44])
        self.assertFalse(set(p['participants']) & {6,10,12,19,21,36,37,42,45,49,9,13,15,16,17,22,27,30,33,38,48,51})


if __name__ == '__main__':
    unittest.main()

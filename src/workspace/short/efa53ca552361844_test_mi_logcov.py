import unittest
from mi_logcov_comparison import (log_features, independent_features, source_indices,
    validation_history, feature_columns, logistic_terms, independent_classifier,
    fit_classifier, read, PROTOCOL, UPPER, DIAGONAL)
import numpy as np


class LogCovarianceTests(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(42)
        self.wave = self.rng.normal(size=(8, 500))
        self.wave -= self.wave.mean(0)

    def test_car_singular_covariance_log_is_finite_and_matches_schur(self):
        self.assertLess(np.linalg.matrix_rank(np.cov(self.wave)), 8)
        actual = log_features(self.wave)
        self.assertEqual(actual.shape, (36,))
        np.testing.assert_allclose(actual, independent_features(self.wave), rtol=5e-9, atol=5e-9)

    def test_amplitude_and_dc_invariance(self):
        expected = log_features(self.wave)
        np.testing.assert_allclose(log_features(self.wave * 100), expected, rtol=5e-9, atol=5e-9)
        np.testing.assert_allclose(log_features(self.wave + np.arange(8)[:, None]*100), expected, rtol=5e-9, atol=5e-9)

    def test_weighted_triangle_preserves_matrix_frobenius_norm(self):
        vector = log_features(self.wave)
        matrix = np.zeros((8, 8)); values = vector.copy()
        values[UPPER[0] != UPPER[1]] /= np.sqrt(2)
        matrix[UPPER] = values
        matrix += np.triu(matrix, 1).T
        self.assertAlmostEqual(float(vector @ vector), float(np.sum(matrix*matrix)), places=11)

    def test_permutation_equivariance_not_automatic_identity_invariance(self):
        def matrix(wave):
            vector = log_features(wave).copy()
            vector[UPPER[0] != UPPER[1]] /= np.sqrt(2)
            result = np.zeros((8,8)); result[UPPER] = vector
            return result + np.triu(result, 1).T
        perm = [7,6,5,4,3,2,1,0]
        np.testing.assert_allclose(matrix(self.wave[perm]), matrix(self.wave)[np.ix_(perm,perm)], rtol=5e-9, atol=5e-9)

    def test_diagonal_control_exact_positions(self):
        np.testing.assert_array_equal(feature_columns('LOGCOV_DIAG_LR'), [0,8,15,21,26,30,33,35])
        np.testing.assert_array_equal(feature_columns('LOGCOV_FULL_LR'), np.arange(36))
        self.assertEqual(len(DIAGONAL), 8)
        with self.assertRaises(ValueError): feature_columns('CSP')

    def test_nonfinite_flat_wrong_shape_fail(self):
        for wave in (np.zeros((8,500)), np.ones((8,500)), np.ones((8,499)), np.full((8,500), np.nan)):
            with self.assertRaises(ValueError): log_features(wave)

    def test_source_people_separation_and_target_not_fitted(self):
        subjects = np.repeat(np.arange(1,31), 4)
        fold = {'person':30,'fit_people':list(range(1,27)),'validation_people':[27,28,29]}
        fit, val = source_indices(fold, subjects)
        self.assertEqual((len(fit),len(val)), (104,12))
        self.assertFalse(set(subjects[fit]) & set(subjects[val]))
        self.assertNotIn(30,subjects[fit]); self.assertNotIn(30,subjects[val])
        fold['fit_people'][-1] = 30
        with self.assertRaises(ValueError): source_indices(fold, subjects)

    def test_validation_tie_prefers_strongest_C(self):
        selected, history = validation_history(np.zeros((4,8)),np.zeros(4),np.zeros((12,8)),
            np.tile([0,1],6),np.repeat([27,28,29],4),[27,28,29],[.01,.1,1,10])
        self.assertEqual(selected, 0); self.assertEqual(len(history),4)
        self.assertEqual(history[0]['C'],.01)

    def test_validation_uses_equal_person_means_not_pooled_windows(self):
        subjects = np.repeat([1,2,3],[4,4,8]); y = np.tile([0,1],8)
        z = (2*y-1).astype(float)[:,None]; z[subjects == 3] *= -1
        _, history = validation_history(np.ones((1,1)),np.zeros(1),z,y,subjects,[1,2,3],[1])
        self.assertAlmostEqual(history[0]['mean_person_ba'], 2/3)

    def test_logistic_gradient_hessian_finite_difference(self):
        z = self.rng.normal(size=(40,4)); y = np.arange(40)%2
        beta = self.rng.normal(size=5); epsilon = 1e-5
        _, gradient, hessian = logistic_terms(beta,z,y,.1)
        ng, nh = [], []
        for i in range(5):
            direction = np.eye(5)[i]*epsilon
            plus, gp, _ = logistic_terms(beta+direction,z,y,.1)
            minus, gm, _ = logistic_terms(beta-direction,z,y,.1)
            ng.append((plus-minus)/(2*epsilon)); nh.append((gp-gm)/(2*epsilon))
        np.testing.assert_allclose(gradient, ng, rtol=1e-6, atol=1e-6)
        np.testing.assert_allclose(hessian, np.array(nh).T, rtol=1e-6, atol=1e-6)

    def test_independent_newton_matches_lbfgs(self):
        z = self.rng.normal(size=(100,8)); y = np.arange(100)%2
        for c in (.01,10):
            model = fit_classifier(z,y,c,read(PROTOCOL)['classifier'])
            beta, gradient = independent_classifier(z,y,c)
            self.assertLessEqual(gradient,1e-6)
            np.testing.assert_allclose(np.r_[model.coef_[0],model.intercept_],beta,rtol=5e-4,atol=2e-5)
            np.testing.assert_array_equal(model.predict(z),(z@beta[:-1]+beta[-1]>0).astype(int))

    def test_protocol_fixed_scope_and_zero_personal_labels(self):
        p = read(PROTOCOL)
        self.assertEqual(p['channels'],['F3','F4','C3','C4','T7','T8','O1','O2'])
        self.assertEqual(len(p['participants']),30)
        self.assertFalse(set(p['participants']) & {6,10,12,19,21,36,37,42,45,49,9,13,15,16,17,22,27,30,33,38,48,51})
        self.assertFalse(p['personal_labels_used']); self.assertEqual(p['primary_reference'],'CROSS_SOURCE_BN')
        self.assertEqual(p['classifier']['C_in_tie_preference_order'],[.01,.1,1,10])


if __name__ == '__main__':
    unittest.main()

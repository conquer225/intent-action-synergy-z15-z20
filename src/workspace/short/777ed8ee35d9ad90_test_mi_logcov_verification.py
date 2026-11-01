"""Supplemental numerical-verification fixtures; no dataset/model scores."""
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch
import verify_mi_logcov_stabilized as verifier
import numpy as np
from scipy.optimize import minimize


class NewtonVerificationTests(TestCase):
    def setUp(self):
        self.z = np.random.default_rng(102).normal(size=(96, 3))
        self.y = np.tile([0, 1], 48)
        verifier.TRACE.clear()

    def test_refines_stalled_independent_solution_without_saved_weights(self):
        terms = verifier.frozen_driver.logistic_terms
        solved = minimize(lambda b: terms(b, self.z, self.y, .1)[0], np.zeros(4),
            jac=lambda b: terms(b, self.z, self.y, .1)[1],
            hess=lambda b: terms(b, self.z, self.y, .1)[2], method='trust-exact',
            options={'gtol': 1e-7, 'maxiter': 200})
        approximate = SimpleNamespace(x=solved.x+2e-8, success=False, message='fixture precision stall')
        with patch.object(verifier, 'minimize', return_value=approximate):
            beta, gradient = verifier.stabilized_classifier(self.z, self.y, .1)
        self.assertLessEqual(gradient, 1e-6)
        np.testing.assert_allclose(beta, solved.x, rtol=1e-6, atol=1e-8)
        self.assertGreater(len(verifier.TRACE[-1]['steps']), 0)
        self.assertLess(gradient, verifier.TRACE[-1]['initial_gradient'])

    def test_nonfinite_solution_is_rejected(self):
        invalid = SimpleNamespace(x=np.full(4, np.nan), success=False, message='nonfinite fixture')
        with patch.object(verifier, 'minimize', return_value=invalid), np.errstate(invalid='ignore'):
            with self.assertRaises(ValueError):
                verifier.stabilized_classifier(self.z, self.y, .1)
        self.assertEqual(verifier.TRACE, [])

    def test_solver_does_not_weaken_original_gradient_bound(self):
        _, gradient = verifier.stabilized_classifier(self.z, self.y, 10)
        self.assertLessEqual(gradient, 1e-6)
        self.assertTrue(verifier.TRACE[-1]['trust_exact_success'])


if __name__ == '__main__':
    main()

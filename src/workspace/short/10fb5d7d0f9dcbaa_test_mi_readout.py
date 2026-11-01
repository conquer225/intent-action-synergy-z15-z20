"""Synthetic fixtures only; no new EEG validation scores."""
from pathlib import Path
from unittest import TestCase, main
import mi_readout_diagnostic as experiment
import numpy as np
from sklearn.kernel_approximation import RBFSampler
from sklearn.preprocessing import StandardScaler


class ReadoutTests(TestCase):
    def setUp(self):
        self.z = StandardScaler().fit_transform(np.random.default_rng(813).normal(size=(120, 36)))

    def test_sampler_matches_independent_rng_all_seeds(self):
        for seed in (42, 43, 44):
            actual = experiment.random_map(seed)
            other = experiment.random_map(seed, alternate=True)
            np.testing.assert_allclose(actual[0], other[0], rtol=1e-15, atol=1e-15)
            np.testing.assert_array_equal(actual[1], other[1])

    def test_numeric_gamma_map_depends_on_dimension_not_dummy_values(self):
        for dummy in (np.zeros((1, 36)), np.full((17, 36), 999.)):
            fitted = RBFSampler(gamma=1/72, n_components=128, random_state=42).fit(dummy)
            np.testing.assert_array_equal(fitted.random_weights_, experiment.random_map(42)[0])
            np.testing.assert_array_equal(fitted.random_offset_, experiment.random_map(42)[1])

    def test_primary_and_complex_maps_agree(self):
        for method in experiment.METHODS[1:]:
            for seed in (42, 43, 44):
                np.testing.assert_allclose(experiment.auxiliary(self.z, method, seed),
                    experiment.auxiliary(self.z, method, seed, alternate=True), rtol=5e-12, atol=5e-12)

    def test_two_blocks_have_equal_source_energy(self):
        for method in experiment.METHODS[1:]:
            values, mean, scale = experiment.augmented_fit(self.z, method, 42)
            self.assertEqual(values.shape, (120, 164))
            np.testing.assert_allclose(values.mean(0), 0, atol=1e-13)
            self.assertAlmostEqual(np.mean(np.sum(values[:, :36]**2, axis=1)), 18)
            self.assertAlmostEqual(np.mean(np.sum(values[:, 36:]**2, axis=1)), 18)
            np.testing.assert_array_equal(values, experiment.augmented_apply(self.z, method, 42, mean, scale))

    def test_apply_does_not_refit_statistics_on_shifted_validation(self):
        for method in experiment.METHODS[1:]:
            _, mean, scale = experiment.augmented_fit(self.z, method, 42)
            before = mean.copy()
            validation = self.z[:9]+3
            expected = (experiment.auxiliary(validation, method, 42)-mean)*scale
            actual = experiment.augmented_apply(validation, method, 42, mean, scale)
            np.testing.assert_array_equal(mean, before)
            np.testing.assert_allclose(actual[:, 36:], expected)
            self.assertGreater(np.max(np.abs(actual.mean(0))), .1)

    def test_projected_head_is_still_affine_in_original_z(self):
        values, mean, scale = experiment.augmented_fit(self.z, 'LINEAR_PROJECTED', 42)
        weights, _ = experiment.random_map(42)
        beta = np.random.default_rng(713).normal(size=165)
        effective = beta[:36]/np.sqrt(2)+(weights/np.sqrt(128))@beta[36:-1]*scale
        intercept = beta[-1]-mean@beta[36:-1]*scale
        np.testing.assert_allclose(values@beta[:-1]+beta[-1], self.z@effective+intercept, rtol=1e-12, atol=1e-12)

    def test_rff_has_curvature_not_only_redundant_projection(self):
        z = np.stack((np.zeros(36), np.ones(36), -np.ones(36)))
        for seed in (42, 43, 44):
            mapped = experiment.auxiliary(z, 'LINEAR_RFF', seed)
            self.assertGreater(np.linalg.norm(mapped[1]+mapped[2]-2*mapped[0]), .01)
            linear = experiment.auxiliary(z, 'LINEAR_PROJECTED', seed)
            np.testing.assert_allclose(linear[1]+linear[2]-2*linear[0], 0, atol=1e-14)

    def test_rejects_nonfinite_wrong_shape_or_undeclared_configuration(self):
        for z in (np.zeros((0, 36)), np.zeros((10, 35)), np.full((10, 36), np.nan)):
            with self.assertRaises(ValueError):
                experiment.auxiliary(z, 'LINEAR_RFF', 42)
        for method, seed in (('LINEAR', 42), ('unknown', 42), ('LINEAR_RFF', 99)):
            with self.assertRaises(ValueError):
                experiment.auxiliary(self.z, method, seed)
        with self.assertRaises(ValueError):
            experiment.augmented_apply(self.z, 'LINEAR_RFF', 42, np.zeros(128), 0)

    def test_rejects_flat_auxiliary_without_imputation(self):
        for method in experiment.METHODS[1:]:
            with self.assertRaises(ValueError):
                experiment.augmented_fit(np.zeros((10, 36)), method, 42)

    def test_seed_appearance_and_person_averaging(self):
        appearances = {1: [], 2: []}
        for seed in (42, 43, 44):
            appearances[1] += [{'seed': seed, 'ba': .8, 'macro_f1': .7}]*5
            appearances[2] += [{'seed': seed, 'ba': .2, 'macro_f1': .3}]
        rows = experiment.aggregate(appearances, [42, 43, 44])
        self.assertAlmostEqual(np.mean([row['ba'] for row in rows]), .5)
        self.assertEqual(rows[0]['per_seed'][0]['appearances'], 5)
        self.assertEqual(rows[1]['per_seed'][0]['appearances'], 1)
        with self.assertRaises(ValueError):
            experiment.aggregate({1: appearances[1][:5]}, [42, 43, 44])

    def test_gate_requires_gain_interval_and_weak_people(self):
        settings = {'minimum_gain': .02, 'lower_greater_than': 0, 'lowest7_drop_at_most': .01}
        self.assertTrue(experiment.direction_gate([.03, .03], [.01, .04], -.005, settings))
        self.assertFalse(experiment.direction_gate([.015, .015], [.01, .04], 0, settings))
        self.assertFalse(experiment.direction_gate([.03, .03], [-.001, .04], 0, settings))
        self.assertFalse(experiment.direction_gate([.03, .03], [.01, .04], -.02, settings))

    def test_protocol_preserves_boundaries_and_two_co_primary_controls(self):
        p = experiment.read(Path(experiment.PROTOCOL))
        self.assertEqual(p['channels'], ['F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2'])
        self.assertEqual(p['seeds'], [42, 43, 44])
        self.assertEqual(p['mapping']['components'], 128)
        self.assertEqual(p['classifier']['C'], .1)
        self.assertEqual(p['bootstrap']['co_primary_coverage'], .975)
        self.assertEqual([row['reference'] for row in p['co_primary']], ['LINEAR', 'LINEAR_PROJECTED'])
        self.assertFalse(p['outer_target_scored'] or p['board_accessed'] or p['arm_exported'])
        self.assertEqual(experiment.method_seeds('LINEAR', p), [0])
        self.assertEqual(experiment.method_seeds('LINEAR_RFF', p), [42, 43, 44])


if __name__ == '__main__':
    main()

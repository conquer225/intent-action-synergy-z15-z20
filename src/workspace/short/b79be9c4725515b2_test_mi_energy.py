from unittest import TestCase, main
import mi_energy_diagnostic as m
import numpy as np
from sklearn.preprocessing import StandardScaler


class EnergyTests(TestCase):
    def setUp(self):
        self.wave = np.random.default_rng(121).normal(size=(8, 500))
        self.wave -= self.wave.mean(0)

    def test_dimensions_and_normalized_reference(self):
        values = m.features(self.wave)
        self.assertEqual([len(values[method]) for method in m.METHODS], [36, 37, 36])
        np.testing.assert_array_equal(values['NORMALIZED'], m.prior.prior_math.log_features(self.wave))
        np.testing.assert_array_equal(values['NORMALIZED_ENERGY'][:36], values['NORMALIZED'])

    def test_direct_schur_log_of_absolute_covariance(self):
        original, alternate = m.features(self.wave), m.features(self.wave, alternate=True)
        for method in m.METHODS:
            np.testing.assert_allclose(original[method], alternate[method], rtol=5e-9, atol=5e-9)

    def test_amplitude_retained_only_in_energy_branches(self):
        original = m.features(self.wave)
        changed = m.features(self.wave*7)
        np.testing.assert_allclose(original['NORMALIZED'], changed['NORMALIZED'], rtol=5e-9, atol=5e-9)
        self.assertAlmostEqual(changed['NORMALIZED_ENERGY'][-1]-original['NORMALIZED_ENERGY'][-1], np.log(49))
        delta = np.zeros(36)
        delta[m.DIAGONAL] = np.log(49)
        np.testing.assert_allclose(changed['ABSOLUTE']-original['ABSOLUTE'], delta, rtol=5e-9, atol=5e-9)

    def test_absolute_identity_and_cached_shape_are_not_mutated(self):
        shape = m.prior.prior_math.log_features(self.wave)
        saved = shape.copy()
        values = m.features(self.wave, shape)
        expected = values['NORMALIZED'].copy()
        expected[m.DIAGONAL] += values['NORMALIZED_ENERGY'][-1]
        np.testing.assert_array_equal(expected, values['ABSOLUTE'])
        np.testing.assert_array_equal(shape, saved)

    def test_dc_offset_and_time_permutation_leave_features(self):
        changed = self.wave[:, np.random.default_rng(122).permutation(500)]+np.arange(8)[:, None]*100
        original, shifted = m.features(self.wave), m.features(changed)
        for method in m.METHODS:
            np.testing.assert_allclose(original[method], shifted[method], rtol=5e-9, atol=5e-9)

    def test_sum_variances_equals_trace_of_covariance(self):
        expected = np.log(np.trace(np.cov(self.wave)))
        self.assertAlmostEqual(m.features(self.wave)['NORMALIZED_ENERGY'][-1], expected, places=13)

    def test_guard_no_silent_trial_deletion_or_imputation(self):
        for wave in (self.wave[:, :499], np.zeros((8, 500)), np.ones((8, 500)), np.full((8, 500), np.nan)):
            with self.assertRaises(ValueError):
                m.features(wave)
        with self.assertRaises(ValueError):
            m.features(self.wave, np.zeros(35))

    def test_source_standardized_old_columns_unchanged(self):
        rows = np.random.default_rng(123).normal(size=(100, 37))
        expanded = StandardScaler().fit_transform(rows)
        original = StandardScaler().fit_transform(rows[:, :36])
        np.testing.assert_array_equal(expanded[:, :36], original)
        self.assertAlmostEqual(np.mean(np.sum(expanded*expanded, axis=1)), 37)

    def test_common_unit_log_shift_absorbed_by_fitting_mean(self):
        rng = np.random.default_rng(125)
        waves = [rng.normal(size=(8, 500))*np.exp(i/30) for i in range(12)]
        a = np.stack([m.features(wave)['NORMALIZED_ENERGY'] for wave in waves])
        b = np.stack([m.features(wave*1000)['NORMALIZED_ENERGY'] for wave in waves])
        np.testing.assert_allclose(StandardScaler().fit_transform(a), StandardScaler().fit_transform(b), rtol=5e-8, atol=5e-8)

    def test_validation_transform_does_not_update_source_statistics(self):
        source = np.random.default_rng(124).normal(size=(80, 37))
        scaler = StandardScaler().fit(source)
        mean, scale = scaler.mean_.copy(), scaler.scale_.copy()
        scaler.transform(source+1000)
        np.testing.assert_array_equal(scaler.mean_, mean)
        np.testing.assert_array_equal(scaler.scale_, scale)

    def test_primary_gate_requires_every_clause(self):
        gate = {'gain_at_least': .02, 'descriptive_paired_lower_greater_than': 0, 'lowest7_mean_drop_at_most': .01}
        self.assertTrue(m.primary_gate(.02, .001, -.01, gate))
        for gain, lower, weak in ((.0199, .001, 0), (.03, 0, 0), (.03, .001, -.0101)):
            self.assertFalse(m.primary_gate(gain, lower, weak, gate))

    def test_people_equal_weight_despite_validation_repetition(self):
        rows = m.prior.average_appearances({1: [{'ba': .5, 'macro_f1': .4}], 2: [{'ba': 1., 'macro_f1': 1.}]*7})
        self.assertAlmostEqual(np.mean([row['ba'] for row in rows]), .75)

    def test_fixed_protocol_and_finite_budget(self):
        protocol = m.read(m.PROTOCOL)
        self.assertEqual(protocol['channels'], ['F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2'])
        self.assertEqual(tuple(protocol['methods']), m.METHODS)
        self.assertEqual(protocol['primary_candidate'], 'NORMALIZED_ENERGY')
        self.assertEqual(protocol['classifier']['C'], .1)
        self.assertFalse(protocol['outer_target_scored'])
        self.assertFalse(protocol['board_accessed'])


if __name__ == '__main__':
    main()

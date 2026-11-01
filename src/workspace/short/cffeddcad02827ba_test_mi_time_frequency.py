from unittest import TestCase, main
import mi_time_frequency_diagnostic as m
import numpy as np
from sklearn.preprocessing import StandardScaler


class TimeFrequencyTests(TestCase):
    def setUp(self):
        self.wave = np.random.default_rng(81).normal(size=(8,500))
        self.wave -= self.wave.mean(0)

    def test_whole_bridge_and_declared_dimensions(self):
        actual=m.features(self.wave)
        np.testing.assert_allclose(actual['WHOLE'],m.prior_math.log_features(self.wave),rtol=5e-9,atol=5e-9)
        self.assertEqual([len(actual[k]) for k in m.METHODS],[36,72,72,144])

    def test_whole_discards_sample_order_but_time_features_do_not(self):
        shuffled=self.wave[:,np.random.default_rng(82).permutation(500)]
        original=m.features(self.wave); changed=m.features(shuffled)
        np.testing.assert_allclose(original['WHOLE'],changed['WHOLE'],rtol=5e-9,atol=5e-9)
        self.assertGreater(np.linalg.norm(original['TIME2']-changed['TIME2']),.01)

    def test_half_swap_has_fixed_block_identity(self):
        swapped=np.concatenate([self.wave[:,250:],self.wave[:,:250]],axis=1)
        a,b=m.features(self.wave),m.features(swapped)
        np.testing.assert_allclose(a['WHOLE'],b['WHOLE'],rtol=5e-9,atol=5e-9)
        np.testing.assert_allclose(a['TIME2'].reshape(2,36)[::-1].ravel(),b['TIME2'],rtol=5e-9,atol=5e-9)
        np.testing.assert_allclose(a['TIME2_FREQ2'].reshape(2,2,36)[::-1].ravel(),b['TIME2_FREQ2'],rtol=5e-9,atol=5e-9)

    def test_complementary_frequency_masks_restore_all_input_bins(self):
        low,high=m.split_frequency(self.wave)
        np.testing.assert_allclose(low+high,self.wave,rtol=1e-12,atol=1e-12)
        alternate=m.split_frequency(self.wave,True)
        for actual,expected in zip(alternate,(low,high)):
            np.testing.assert_allclose(actual,expected,rtol=1e-12,atol=1e-12)

    def test_exact14hz_boundary_is_in_high_component(self):
        wave=np.arange(1,9)[:,None]*np.sin(2*np.pi*14*np.arange(500)/250)[None,:]
        low,high=m.split_frequency(wave)
        np.testing.assert_allclose(low,0,rtol=0,atol=1e-12)
        np.testing.assert_allclose(high,wave,rtol=1e-12,atol=1e-12)

    def test_frequency_covariances_sum_without_whole_cross_term(self):
        low,high=m.split_frequency(self.wave)
        lc,hc=low-low.mean(1,keepdims=True),high-high.mean(1,keepdims=True)
        np.testing.assert_allclose(lc@hc.T/499,0,rtol=0,atol=1e-12)
        np.testing.assert_allclose(np.cov(low)+np.cov(high),np.cov(self.wave),rtol=1e-12,atol=1e-12)

    def test_whole_amplitude_and_dc_are_removed(self):
        a=m.features(self.wave);b=m.features(100*self.wave+np.arange(8)[:,None]*100)
        for method in m.METHODS:
            np.testing.assert_allclose(a[method],b[method],rtol=5e-9,atol=5e-9)

    def test_common_parent_trace_preserves_relative_component_energy(self):
        section=self.wave[:,:250].T
        a=m.segment_log(section,1);b=m.segment_log(section*2,1)
        delta=b-a; expected=np.zeros(36);expected[m.prior_math.DIAGONAL]=np.log(4)
        np.testing.assert_allclose(delta,expected,rtol=5e-9,atol=5e-9)

    def test_independent_schur_and_scipy_fft_features_match(self):
        a=m.features(self.wave);b=m.features(self.wave,True)
        for method in m.METHODS:
            np.testing.assert_allclose(a[method],b[method],rtol=5e-9,atol=5e-9)

    def test_invalid_or_degenerate_component_is_not_imputed(self):
        invalid=[np.zeros((8,500)),np.ones((8,500)),np.full((8,500),np.nan),self.wave[:,:499]]
        for wave in invalid:
            with self.subTest(shape=wave.shape):
                with self.assertRaises(ValueError):m.features(wave)
        low_only=np.arange(1,9)[:,None]*np.sin(2*np.pi*10*np.arange(500)/250)[None,:]
        with self.assertRaises(ValueError):m.features(low_only)

    def test_source_people_disjoint_and_outer_person_not_scored(self):
        people=np.repeat(np.arange(1,31),2)
        fold={'target':1,'fit_people':list(range(2,28)),'validation_people':[28,29,30]}
        fit,val=m.source_indices(fold,people)
        self.assertNotIn(1,people[fit]);self.assertNotIn(1,people[val]);self.assertFalse(set(fit)&set(val))
        fold['validation_people']=[1,29,30]
        with self.assertRaises(ValueError):m.source_indices(fold,people)

    def test_each_person_has_equal_weight_despite_repeated_appearances(self):
        rows=m.average_appearances({1:[{'ba':.5,'macro_f1':.4}],2:[{'ba':1.,'macro_f1':1.}]*7})
        self.assertAlmostEqual(np.mean([r['ba'] for r in rows]),.75)
        self.assertNotAlmostEqual(np.mean([r['ba'] for row in rows for r in row['appearances']]),.75)

    def test_dimension_factor_preserves_source_mean_squared_norm(self):
        for dimension in (36,72,144):
            x=np.random.default_rng(83).normal(size=(96,dimension))
            z=StandardScaler().fit_transform(x)*np.sqrt(36/dimension)
            self.assertAlmostEqual(float(np.mean(np.sum(z*z,axis=1))),36,places=10)

    def test_protocol_has_no_outer_scoring_or_parameter_search(self):
        p=m.read(m.PROTOCOL)
        self.assertEqual(p['channels'],['F3','F4','C3','C4','T7','T8','O1','O2'])
        self.assertEqual(p['classifier']['C'],.1)
        self.assertFalse(p['outer_target_scored']);self.assertFalse(p['board_accessed'])
        self.assertEqual(tuple(p['methods']),m.METHODS)


if __name__=='__main__':main()

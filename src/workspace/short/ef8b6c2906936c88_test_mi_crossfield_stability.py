import inspect
import json
from pathlib import Path
import unittest

from mi_crossfield_stability import (bounded_risk_weights, sample_weights, average_states,
                                     recalibrate_bn, train_source, PROTOCOL)
from mi_comparison_models import EEGNetSmall, network_logits, torch
import numpy as np


class CrossfieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads(PROTOCOL.read_text(encoding='utf-8'))
        cls.config = json.loads((PROTOCOL.parent/'mi_model_comparison_protocol.json').read_text(encoding='utf-8'))['eegnet']
        torch.set_num_threads(2)

    def test_fixed_original_scope_and_no_confirmation(self):
        p = self.protocol
        original = json.loads((PROTOCOL.parent/'cho2017_protocol.json').read_text(encoding='utf-8'))
        self.assertEqual(p['channels'], ['F3','F4','C3','C4','T7','T8','O1','O2'])
        self.assertEqual(len(p['participants']), 30)
        self.assertFalse(set(p['participants']) & {9,13,15,16,17,22,27,30,33,38,48,51})
        self.assertFalse(set(p['participants']) & {6,10,12,19,21,36,37,42,45,49})
        self.assertEqual(p['seeds'], [42,43,44])

    def test_equal_risk_uniform(self):
        np.testing.assert_allclose(bounded_risk_weights(np.ones(26), self.protocol['risk']), np.full(26, 1/26), atol=1e-15)

    def test_extreme_risk_respects_budget_and_monotonicity(self):
        for risks in (np.arange(26)*100., np.r_[np.zeros(24), 1., 1e6], np.linspace(0, 1, 26)):
            weights = bounded_risk_weights(risks, self.protocol['risk'])
            self.assertGreaterEqual(weights.min(), .5/26-1e-15)
            self.assertLessEqual(weights.max(), 2/26+1e-15)
            self.assertAlmostEqual(weights.sum(), 1., places=12)
            self.assertTrue((np.diff(weights) >= -1e-15).all())

    def test_weights_permutation_invariant(self):
        risks = np.random.default_rng(4).normal(size=26)
        order = np.random.default_rng(5).permutation(26)
        np.testing.assert_allclose(bounded_risk_weights(risks, self.protocol['risk'])[order],
                                   bounded_risk_weights(risks[order], self.protocol['risk']), atol=1e-15)

    def test_invalid_risk_rejected(self):
        for risks in ([1.], [1., np.nan], [[1., 2.]]):
            with self.assertRaises(ValueError):
                bounded_risk_weights(risks, self.protocol['risk'])

    def test_person_equal_not_window_equal(self):
        people = np.array([1,1,2,2,2,2])
        weights, _, _, _ = sample_weights(people, np.array([.5,.5]))
        np.testing.assert_allclose(weights, [1.5,1.5,.75,.75,.75,.75])
        losses = np.array([2.,2.,4.,4.,4.,4.])
        self.assertAlmostEqual(np.mean(weights*losses), 3.)
        weights, _, _, _ = sample_weights(people, np.array([.25,.75]))
        self.assertAlmostEqual(np.mean(weights*losses), 3.5)

    def test_average_float_not_integer_counters(self):
        states = [{'a': torch.tensor([1.,2.]), 'n': torch.tensor(2)},
                  {'a': torch.tensor([3.,6.]), 'n': torch.tensor(4)}]
        mean = average_states(states, states[0])
        torch.testing.assert_close(mean['a'], torch.tensor([2.,4.]))
        self.assertEqual(mean['n'].item(), 2)

    def test_bn_calibration_has_no_weight_gradient_or_dropout(self):
        torch.manual_seed(1)
        model = EEGNetSmall(self.config)
        parameters = {key: value.detach().clone() for key, value in model.named_parameters()}
        states = torch.random.get_rng_state().clone()
        recalibrate_bn(model, torch.ones(12,1,8,500), batch_size=4)
        torch.testing.assert_close(torch.random.get_rng_state(), states, rtol=0, atol=0)
        for key, value in model.named_parameters():
            torch.testing.assert_close(value, parameters[key], rtol=0, atol=0)
            self.assertIsNone(value.grad)
        self.assertEqual(model.block1[0].num_batches_tracked.item(), 3)
        self.assertFalse(model.training)
        self.assertTrue(all(not layer.training for layer in model.modules()))
        self.assertEqual(model.block1[0].momentum, self.config['bn_torch_momentum'])

    def test_training_api_cannot_receive_target(self):
        self.assertFalse(any('target' in name for name in inspect.signature(train_source).parameters))

    def test_source_overlap_rejected(self):
        with self.assertRaises(ValueError):
            train_source(None, None, np.array([1]), None, None, np.array([1]),
                         self.config, self.protocol['risk'], self.protocol['average'], 'PERSON_EQUAL', 42)

    def test_synthetic_reproducible_and_epoch_lag(self):
        torch.manual_seed(9)
        x = torch.randn(12,1,8,500)
        y = np.arange(12)%2
        people = np.repeat([1,2], 6)
        config = {**self.config, 'epochs_max': 3, 'batch_size': 6}
        risk = {**self.protocol['risk'], 'warmup_epochs': 1}
        args = (x, y, people, x[:4], y[:4], np.full(4, 3), config, risk,
                self.protocol['average'], 'BOUNDED_RISK', 42)
        a = train_source(*args)
        b = train_source(*args)
        for state in (0,1):
            for key in a[state]:
                torch.testing.assert_close(a[state][key], b[state][key], rtol=0, atol=0)
        h = a[3]['history']
        np.testing.assert_allclose(h[0]['group_weights_used'], [.5,.5])
        np.testing.assert_allclose(h[1]['group_weights_used'], bounded_risk_weights(h[0]['source_ema_ce'], risk), atol=1e-15)
        self.assertEqual(a[3]['averaged_epochs'], [1,2,3])
        self.assertFalse(a[3]['average_source_validation_used_to_select'])


if __name__ == '__main__':
    unittest.main()

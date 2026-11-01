import inspect
import json
from pathlib import Path
import unittest

from mi_bn_trainonly import calibration_indices, compare_non_bn, BASES, PROTOCOL
from mi_crossfield_stability import recalibrate_bn
from mi_comparison_models import EEGNetSmall, torch
import numpy as np


class BNTrainOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)
        cls.config = json.loads((Path(__file__).parent / 'mi_model_comparison_protocol.json').read_text(encoding='utf-8'))['eegnet']

    def case(self):
        people = np.repeat([1, 2, 3], 200)
        order = np.tile(np.arange(200), 3)
        case = {'person': 1, 'seed': 42, 'personal_fit': list(range(80)),
                'personal_validation': list(range(80, 120)), 'test': list(range(120, 200)),
                'matched_fit': list(range(200, 280)), 'matched_validation': list(range(400, 440)),
                'original_source_fold': {'fit_people': [2], 'validation_people': [3], 'target': 1}}
        return case, people, order

    def test_fixed_scope_and_two_primary_pairs(self):
        p = json.loads(PROTOCOL.read_text(encoding='utf-8'))
        self.assertEqual(p['channels'], ['F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2'])
        self.assertEqual(len(p['participants']), 30)
        self.assertEqual(p['seeds'], [42, 43, 44])
        self.assertEqual(len(p['primary_comparisons']), 2)
        self.assertEqual(p['bootstrap']['primary_interval'], .975)
        self.assertFalse(set(p['participants']) & {6,9,10,12,13,15,16,17,19,21,22,27,30,33,36,37,38,42,45,48,49,51})
        self.assertFalse(p['new_gradient_training'] or p['deployment_authorized'])
        self.assertEqual(set(BASES), {'CROSS_SOURCE_BN', 'PERSON_BN', 'MATCHED80_BN'})

    def test_source_excludes_target_and_validation(self):
        c, people, order = self.case()
        indices = calibration_indices(c, people, order, 'CROSS_SOURCE_BN')
        np.testing.assert_array_equal(indices, np.arange(200, 400))

    def test_person_only_original_first80(self):
        c, people, order = self.case()
        np.testing.assert_array_equal(calibration_indices(c, people, order, 'PERSON_BN'), np.arange(80))

    def test_matched_keeps_frozen_indices(self):
        c, people, order = self.case()
        np.testing.assert_array_equal(calibration_indices(c, people, order, 'MATCHED80_BN'), c['matched_fit'])

    def test_validation_in_fit_rejected(self):
        c, people, order = self.case()
        c['personal_fit'][-1] = 80
        with self.assertRaises(AssertionError):
            calibration_indices(c, people, order, 'PERSON_BN')
        c['original_source_fold']['fit_people'].append(3)
        with self.assertRaises(ValueError):
            calibration_indices(c, people, order, 'CROSS_SOURCE_BN')

    def test_duplicate_and_unknown_rejected(self):
        c, people, order = self.case()
        c['matched_fit'][-1] = c['matched_fit'][-2]
        with self.assertRaises(ValueError):
            calibration_indices(c, people, order, 'MATCHED80_BN')
        with self.assertRaises(ValueError):
            calibration_indices(c, people, order, 'UNKNOWN')

    def test_learned_tensor_change_rejected(self):
        before = {'dense.weight': torch.ones(2, 3), 'block.running_mean': torch.zeros(3)}
        after = {key: value.clone() for key, value in before.items()}
        after['dense.weight'][0, 0] += 1
        with self.assertRaises(ValueError):
            compare_non_bn(before, after)

    def test_no_change_rejected_and_only_buffers_allowed(self):
        before = {'dense.weight': torch.ones(2, 3), 'block.running_mean': torch.zeros(3)}
        with self.assertRaises(ValueError):
            compare_non_bn(before, before)
        after = {key: value.clone() for key, value in before.items()}
        after['block.running_mean'] += .1
        self.assertEqual(compare_non_bn(before, after), ['block.running_mean'])

    def test_one_batch_moments_remove_initialization(self):
        torch.manual_seed(17)
        model = EEGNetSmall(self.config)
        x = torch.randn(80, 1, 8, 500)
        with torch.no_grad():
            activation = model.temporal(model.temporal_pad(x))
            expected_mean = activation.mean(dim=(0, 2, 3))
            expected_var = activation.var(dim=(0, 2, 3), unbiased=True)
        model.block1[0].running_var.fill_(7)
        parameters = {key: value.detach().clone() for key, value in model.named_parameters()}
        rng = torch.random.get_rng_state().clone()
        recalibrate_bn(model, x, batch_size=256)
        torch.testing.assert_close(model.block1[0].running_mean, expected_mean, rtol=1e-5, atol=1e-6)
        torch.testing.assert_close(model.block1[0].running_var, expected_var, rtol=1e-5, atol=1e-6)
        self.assertEqual(model.block1[0].num_batches_tracked.item(), 1)
        for key, value in model.named_parameters():
            torch.testing.assert_close(parameters[key], value, rtol=0, atol=0)
            self.assertIsNone(value.grad)
        torch.testing.assert_close(rng, torch.random.get_rng_state(), rtol=0, atol=0)
        self.assertTrue(all(not layer.training for layer in model.modules()))
        self.assertEqual(model.block1[0].momentum, .01)

    def test_calibration_has_no_label_argument(self):
        self.assertFalse(any('label' in name for name in inspect.signature(recalibrate_bn).parameters))


if __name__ == '__main__':
    unittest.main()

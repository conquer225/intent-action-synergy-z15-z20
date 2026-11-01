import copy
import unittest
from unittest.mock import patch

import numpy as np
from mi_confirmation import (checked_protocol, source_split, cache_indices, aggregate,
                              paired, gates, detailed_rows)


class ConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.original, cls.selected = checked_protocol()

    def test_source_and_all_target_roles_disjoint(self):
        fit, val = source_split(self.original['train_subjects'])
        self.assertEqual((len(fit), len(val)), (27, 3))
        self.assertEqual(val, [20, 32, 50])
        self.assertEqual(source_split(list(reversed(self.original['train_subjects']))), (fit, val))
        self.assertFalse(set(fit + val) & set(self.p['confirmation_people']))

    def test_non30_source_rejected(self):
        with self.assertRaises(ValueError):
            source_split([1, 2])

    def test_cache_forbidden_people_rejected(self):
        people = np.array(self.p['fit_people'] + self.p['validation_people'])
        fitting, validation = cache_indices({'subjects': people}, self.p)
        self.assertEqual((len(fitting), len(validation)), (27, 3))
        with self.assertRaises(ValueError):
            cache_indices({'subjects': np.append(people, 9)}, self.p)

    def test_metric_is_balanced_and_by_person(self):
        y = np.array([0, 0, 0, 1, 0, 1])
        pred = np.array([0, 0, 0, 0, 1, 0])
        rows = detailed_rows(y, pred, np.array([9, 9, 9, 9, 13, 13]))
        self.assertEqual(rows[0]['balanced_accuracy'], .5)
        self.assertEqual(aggregate(rows, 1)['mean_subject_balanced_accuracy'], .25)

    def test_paired_identity_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            paired([{'subject': 9}], [{'subject': 13}], self.p['bootstrap'])

    def test_absolute_gain_and_intervals_all_required(self):
        primary = {'mean_subject_balanced_accuracy': .65, 'subject_bootstrap_95_ci': [.55, .75]}
        comparison = {'mean_ba_gain': .04, 'paired_bootstrap_95_ci': [.01, .07]}
        self.assertTrue(gates(primary, comparison, primary, self.p)['arm_eligible'])
        bad = copy.deepcopy(comparison); bad['mean_ba_gain'] = .0299
        self.assertFalse(gates(primary, bad, primary, self.p)['arm_eligible'])
        bad = copy.deepcopy(comparison); bad['paired_bootstrap_95_ci'][0] = 0
        self.assertFalse(gates(primary, bad, primary, self.p)['confirmation_gate_passed'])
        bad = copy.deepcopy(primary); bad['subject_bootstrap_95_ci'][0] = .5
        self.assertFalse(gates(bad, comparison, primary, self.p)['confirmation_gate_passed'])

    def test_fixed_seed42_guard_cannot_be_replaced_by_best_seed(self):
        primary = {'mean_subject_balanced_accuracy': .65, 'subject_bootstrap_95_ci': [.55, .75]}
        weak = {'mean_subject_balanced_accuracy': .59, 'subject_bootstrap_95_ci': [.52, .67]}
        comparison = {'mean_ba_gain': .04, 'paired_bootstrap_95_ci': [.01, .07]}
        decision = gates(primary, comparison, weak, self.p)
        self.assertTrue(decision['confirmation_gate_passed'])
        self.assertFalse(decision['arm_eligible'])
        self.assertEqual(self.p['deployment_seed'], 42)

    def test_three_seeds_no_augmentation_no_target_adaptation(self):
        cfg = self.selected['eegnet']
        self.assertEqual(cfg['seeds'], [42, 43, 44])
        self.assertFalse(cfg['augmentation']); self.assertFalse(cfg['target_adaptation'])
        self.assertFalse(self.p['control_enabled']); self.assertFalse(self.p['production_changes_allowed'])

    def test_training_refused_before_any_cache_load_after_target_access(self):
        from mi_confirmation import train
        with patch('mi_confirmation.checked_lock', return_value=(self.p, self.original, self.selected)), \
             patch('mi_confirmation.Path.exists', return_value=True), \
             patch('mi_confirmation.load_run') as cache:
            with self.assertRaises(RuntimeError):
                train()
            cache.assert_not_called()


if __name__ == '__main__':
    unittest.main()

import unittest

import numpy as np

from .seed_fixed8_experiment import INDICES, extract_trial, participant_masks, trial_names


class SeedFixed8Tests(unittest.TestCase):
    def test_exact_mapping(self):
        self.assertEqual(INDICES, (7, 11, 25, 29, 23, 31, 58, 60))

    def test_numeric_trial_sort(self):
        names = trial_names({f"a_eeg{i}": None for i in range(15, 0, -1)})
        self.assertEqual(names[1], "a_eeg2")
        with self.assertRaises(ValueError):
            trial_names({"a_eeg1": None})

    def test_whole_subject_sessions_held_out(self):
        keys = np.array([(s, day, 1, w) for s in (1, 2, 3) for day in (1, 2, 3) for w in (0, 1)])
        train, test = participant_masks(keys, 2)
        self.assertEqual(set(keys[test, 1]), {1, 2, 3})
        self.assertFalse(np.any(train & test))
        self.assertNotIn(2, keys[train, 0])

    def test_causal_features_ignore_future(self):
        raw = np.random.default_rng(2).normal(size=(8, 5200))
        a = extract_trial(raw)
        raw[:, 2800:] += 1000
        b = extract_trial(raw)
        self.assertEqual(a[0].shape, (2, 40))
        self.assertEqual(a[1].shape, (2, 180))
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x[0], y[0])


if __name__ == "__main__":
    unittest.main()

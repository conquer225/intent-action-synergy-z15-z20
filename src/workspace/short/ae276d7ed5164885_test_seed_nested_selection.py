import unittest

import numpy as np

from .seed_nested_selection import nested_splits, participant_score, model_for, CANDIDATES


class NestedTests(unittest.TestCase):
    def test_outer_person_never_in_inner(self):
        groups = np.repeat(np.arange(1, 16), 9)
        for subject in range(1, 16):
            train, test, splits = nested_splits(groups, subject)
            covered = []
            for a, b in splits:
                self.assertFalse(set(groups[a]) & set(groups[b]))
                self.assertNotIn(subject, groups[a])
                self.assertNotIn(subject, groups[b])
                covered.extend(b.tolist())
            self.assertEqual(sorted(covered), train.tolist())
            self.assertEqual(set(groups[test]), {subject})

    def test_all_candidate_pipelines_include_fold_scaler(self):
        for name in CANDIDATES:
            self.assertIn("standardscaler", model_for(name).named_steps)

    def test_scores_are_per_person(self):
        result = participant_score(np.array([0, 1, 0, 1]), np.array([0, 1, 1, 0]), np.array([1, 1, 2, 2]))
        self.assertEqual(result, {1: 1.0, 2: 0.0})


if __name__ == "__main__":
    unittest.main()

"""Train/export behavior on labeled, independently varied synthetic trials."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/workspace/integrations'))
from pl_accel.train import train_model, trial_features


def trials(seed, count):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, .8, (count, 250, 8))
    y = np.arange(count) % 2
    time = np.arange(250) / 250
    for i, label in enumerate(y):
        phase = rng.uniform(0, 6.28)
        x[i, :, 2] += (3 if label else 15)*np.sin(2*np.pi*11*time+phase)
        x[i, :, 3] += (15 if label else 3)*np.sin(2*np.pi*11*time+phase+.2)
    return x, y


class ModelTraining(unittest.TestCase):
    def test_exported_integer_model_separates_held_out_trial_patterns(self):
        x, y = trials(91, 12)
        model = train_model(x, y, window=250, hop=125, feature_count=4)
        holdout, truth = trials(307, 6)
        f = trial_features(holdout, model)
        scores = f.astype(np.int64) @ model.svm.astype(np.int64) + model.bias
        np.testing.assert_array_equal(scores >= 0, truth)
        self.assertEqual(len(model.metadata['selected_features']), 4)
        self.assertEqual(model.metadata['training_trials'], 12)


if __name__ == '__main__':
    unittest.main()

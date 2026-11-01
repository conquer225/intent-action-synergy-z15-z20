import sys
import tempfile
import json
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.training import Dataset, train_mlp, ModelBundle, classification_metrics, DIMENSIONS


def dataset():
    rng = np.random.default_rng(19)
    x, y, groups, splits = [], [], [], []
    for session, split in enumerate(["train", "validation", "test"]):
        for label in range(3):
            for _ in range(20):
                sample = rng.normal(0, .1, 20)
                sample[label] += 4
                x.append(sample); y.append(label); groups.append(f"session-{session}"); splits.append(split)
    return Dataset(np.array(x), np.array(y), np.array(groups), np.array(splits),
                   source="Synthetic unit-test clusters; not wearer performance", source_kind="synthetic")


class TrainingTests(unittest.TestCase):
    def test_all_four_artifacts_share_the_same_integer_interface(self):
        for task, dimension in DIMENSIONS.items():
            with self.subTest(task=task):
                data = dataset()
                x = np.zeros((len(data.x), dimension))
                x[:, :3] = data.x[:, :3]
                data.x = x
                model, metrics = train_mlp(data, task, epochs=30)
                self.assertEqual(model.integer.w1.shape, (32, dimension))
                self.assertGreaterEqual(metrics["test"]["accuracy"], .95)
                self.assertFalse(model.deployable)

    def test_tied_scores_are_invalid_and_rejections_count_as_misses(self):
        model, _ = train_mlp(dataset(), "fatigue", epochs=5)
        class Backend:
            name = "constant-test"
            def infer(self, model, values): return np.zeros(3, np.int32)
        self.assertFalse(model.predict(dataset().x[0], backend=Backend()).valid)
        result = classification_metrics([0, 1, 2], [0, None, 2])
        self.assertEqual(result["samples"], 3)
        self.assertAlmostEqual(result["accuracy"], 2/3)
        self.assertEqual(result["rejected_by_class"], [0, 1, 0])

    def test_provenance_tampering_cannot_promote_synthetic_model(self):
        model, _ = train_mlp(dataset(), "fatigue", epochs=5)
        with tempfile.TemporaryDirectory() as directory:
            model.save(directory)
            path = Path(directory)/"model.json"
            metadata = json.loads(path.read_text())
            metadata["source_kind"] = "recorded"
            path.write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "version"):
                ModelBundle.load(directory)

    def test_groups_cannot_leak_and_normalization_uses_training_only(self):
        data = dataset()
        data.groups[:] = "same-session"
        with self.assertRaisesRegex(ValueError, "leaked"):
            train_mlp(data, "fatigue", epochs=1)
        data = dataset()
        train_mean = data.x[data.splits == "train"].mean(axis=0)
        data.x[data.splits != "train"] += 100
        model, _ = train_mlp(data, "fatigue", epochs=1)
        np.testing.assert_allclose(model.mean, train_mean)

    def test_fixed_mlp_learns_separate_sessions_and_roundtrips_integer_weights(self):
        model, metrics = train_mlp(dataset(), "fatigue", epochs=100, seed=3)
        self.assertGreaterEqual(metrics["test"]["accuracy"], .95)
        self.assertEqual(metrics["test"]["samples"], 60)
        self.assertEqual(model.integer.w1.shape, (32, 20))
        with tempfile.TemporaryDirectory() as directory:
            model.save(directory)
            loaded = ModelBundle.load(directory)
            sample = dataset().x[-1]
            self.assertEqual(loaded.predict(sample).class_id, 2)
            np.testing.assert_array_equal(loaded.predict(sample).scores, model.predict(sample).scores)
            self.assertEqual(loaded.source_kind, "synthetic")
            self.assertFalse(loaded.deployable)


if __name__ == "__main__":
    unittest.main()

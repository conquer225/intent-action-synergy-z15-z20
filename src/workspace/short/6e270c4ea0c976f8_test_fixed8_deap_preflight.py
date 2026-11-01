"""Synthetic structural checks; these are not emotion-accuracy measurements."""

import pickle
import tempfile
import unittest
from pathlib import Path

import numpy as np

from eeg_apps_z15.fixed8_deap_preflight import (
    CYTON_CHANNELS, DEAP_INDICES, audit, inspect_subject, rating_counts,
    subject_paths,
)


class Fixed8DeapPreflightTests(unittest.TestCase):
    def test_exact_electrode_order(self):
        self.assertEqual(CYTON_CHANNELS, ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2"))
        self.assertEqual(DEAP_INDICES, (2, 19, 6, 24, 7, 25, 13, 31))

    def test_rating_policy(self):
        labels = np.zeros((4, 4))
        labels[:, 0] = (3, 5, 7, 4.5)
        self.assertEqual(rating_counts(labels, 0),
                         {"low": 2, "neutral_5_excluded": 1, "high": 1})

    def test_incomplete_dataset_fails_closed(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ValueError, "missing="):
                subject_paths(Path(name))

    def test_shape_rejection(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "s01.dat"
            with path.open("wb") as stream:
                pickle.dump({"data": np.zeros((1, 40, 8064)),
                             "labels": np.zeros((1, 4))}, stream)
            with self.assertRaisesRegex(ValueError, "unexpected shapes"):
                inspect_subject(path)

    def test_missing_directory_does_not_produce_manifest(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaises(FileNotFoundError):
                audit(Path(name) / "absent")


if __name__ == "__main__":
    unittest.main()

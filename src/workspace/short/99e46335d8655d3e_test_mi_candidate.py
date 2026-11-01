import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from mi_candidate import MotorImageryCandidate
from mi_features import CHANNELS, WINDOW_SAMPLES, feature


class MotorImageryCandidateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.model_path = Path(self.directory.name) / "model.npz"
        self.metadata = {"channels": list(CHANNELS), "window_samples": WINDOW_SAMPLES,
                         "source_rate_hz": 250, "control_enabled": False,
                         "promotion_gate_passed": True}
        np.savez(self.model_path, mean=np.zeros(4), scale=np.ones(4),
                 coef=np.ones(4), intercept=0., columns=np.array([2, 3, 10, 11]),
                 metadata=json.dumps(self.metadata))

    def tearDown(self):
        self.directory.cleanup()

    def test_no_cue_or_bad_transport_never_issues_candidate(self):
        model = MotorImageryCandidate(self.model_path)
        eeg = np.ones((WINDOW_SAMPLES, 8))
        quality = np.ones(8)
        self.assertEqual(model.predict(eeg, quality, cue_active=False, transport_ok=True)["state"],
                         "cue_required")
        self.assertEqual(model.predict(eeg, quality, cue_active=True, transport_ok=False)["state"],
                         "transport_invalid")
        quality[2] = 0
        self.assertEqual(model.predict(eeg, quality, cue_active=True, transport_ok=True)["state"],
                         "signal_invalid")

    def test_valid_candidate_is_not_control(self):
        model = MotorImageryCandidate(self.model_path)
        t = np.arange(WINDOW_SAMPLES) / 250
        eeg = np.tile(np.sin(2 * np.pi * 10 * t)[:, None], (1, 8))
        self.assertEqual(feature(eeg).shape, (16,))
        result = model.predict(eeg, np.ones(8), cue_active=True, transport_ok=True)
        self.assertTrue(result["valid"])
        self.assertFalse(result["control_enabled"])

    def test_eight_channel_artifact_requires_all_eight_good(self):
        np.savez(self.model_path, mean=np.zeros(16), scale=np.ones(16),
                 coef=np.ones(16), intercept=0., columns=np.arange(16),
                 metadata=json.dumps(self.metadata))
        model = MotorImageryCandidate(self.model_path)
        self.assertEqual(model.required_indices, tuple(range(8)))
        quality = np.ones(8)
        quality[7] = .49
        result = model.predict(np.zeros((WINDOW_SAMPLES, 8)), quality,
                               cue_active=True, transport_ok=True)
        self.assertEqual(result["state"], "signal_invalid")

    def test_reject_artifact_that_failed_promotion(self):
        self.metadata["promotion_gate_passed"] = False
        np.savez(self.model_path, mean=np.zeros(4), scale=np.ones(4),
                 coef=np.ones(4), intercept=0., columns=np.array([2, 3, 10, 11]),
                 metadata=json.dumps(self.metadata))
        with self.assertRaises(ValueError):
            MotorImageryCandidate(self.model_path)


if __name__ == "__main__":
    unittest.main()

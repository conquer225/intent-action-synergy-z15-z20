import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.legacy_eeg import LegacyEEGFeatures


class LegacyEEGTests(unittest.TestCase):
    def test_continuous_original_features_have_expected_dimensions_and_reset(self):
        adapter = LegacyEEGFeatures()
        rate = 250
        t = np.arange(144*rate)/rate
        rng = np.random.default_rng(11)
        raw = np.stack([12*np.sin(2*np.pi*(7+index*.7)*t)+rng.normal(0, 2, len(t))
                        for index in range(8)], axis=1)
        ready = []
        for start in range(0, len(raw), 250):
            ready.extend(item for item in adapter.feed(raw[start:start+250]) if item["valid"])
        emotion = [o for o in ready if o["task"] == "emotion"]
        fatigue = [o for o in ready if o["task"] == "fatigue"]
        self.assertTrue(emotion)
        self.assertTrue(fatigue)
        self.assertEqual(emotion[-1]["features"].shape, (180,))
        self.assertEqual(fatigue[-1]["features"].shape, (20,))
        self.assertTrue(np.isfinite(fatigue[-1]["features"]).all())
        adapter.reset()
        outputs = adapter.feed(np.zeros((2000, 8)))
        self.assertFalse(any(output["valid"] for output in outputs))


if __name__ == "__main__": unittest.main()

import unittest

import numpy as np
from seed_quality_runtime import SeedQualityRuntime
from seed_replay_check import replay


def weights():
    return {"weight": np.ones((3, 180)), "bias": np.array([-1., 0., 1.]), "classes": np.array([-1, 0, 1])}


class QualityRuntimeTest(unittest.TestCase):
    def test_clean_stream_matches_ungated_reference_and_chunks(self):
        t = np.arange(80*250)/250
        raw = np.stack([20*np.sin(2*np.pi*(9+i*.2)*t+i*.3)+3*np.sin(2*np.pi*5*t) for i in range(8)],axis=1)
        w = weights()
        _,expected,_ = replay(raw,w,250,True)
        first = SeedQualityRuntime(w)
        events = first.append(raw)
        scores = [e["scores"] for e in events if e["valid"]]
        np.testing.assert_allclose(scores,expected,atol=1e-8)
        second = SeedQualityRuntime(w)
        split_events = []
        for i in range(0,len(raw),137):
            split_events.extend(second.append(raw[i:i+137]))
        self.assertEqual(events,split_events)

    def test_bad_segment_freezes_baseline_and_sqi(self):
        r = SeedQualityRuntime(weights())
        for i in range(6):
            r._accept_feature(np.full(180, i+1.))
        mean = r.mean.copy()
        events = r.append(np.zeros((500, 8)))
        self.assertEqual(events[-1]["state"], "rejected")
        np.testing.assert_array_equal(mean, r.mean)
        self.assertEqual(r.accepted_windows, 6)
        self.assertTrue(all(not v for v in r.sqi.reference))
        self.assertIsNone(r.last_prediction)

    def test_disconnect_clears_calibration(self):
        r = SeedQualityRuntime(weights())
        for i in range(6):
            r._accept_feature(np.ones(180))
        r.disconnect()
        self.assertEqual(r.accepted_windows, 0)
        np.testing.assert_array_equal(r.mean, np.zeros(180))
        for i in range(5):
            self.assertFalse(r._accept_feature(np.ones(180))["valid"])
        self.assertTrue(r._accept_feature(np.ones(180))["valid"])

    def test_invalid_transport_and_nonfinite(self):
        r = SeedQualityRuntime(weights())
        self.assertEqual(r.append(np.ones((100,8)), transport_ok=False)[0]["state"], "reset")
        self.assertEqual(r.append(np.full((100,8),np.nan))[0]["state"], "reset")
        self.assertEqual(len(r.pending),0)

    def test_prediction_precedes_mean_update(self):
        r = SeedQualityRuntime(weights())
        for _ in range(5):
            r._accept_feature(np.ones(180))
        out = r._accept_feature(np.ones(180)*2)
        np.testing.assert_allclose(out["scores"], [179,180,181])

    def test_montage_is_not_replaceable(self):
        with self.assertRaises(ValueError):
            SeedQualityRuntime(weights(), channel_map=("F3",)*8)


if __name__ == "__main__":
    unittest.main()

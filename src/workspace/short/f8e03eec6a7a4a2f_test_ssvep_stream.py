import json
import os
import unittest
from pathlib import Path

import numpy as np
from scipy.signal import butter, iirnotch, tf2sos

from ssvep_stream import SSVEPStream


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(Path(__file__).with_name("ssvep_causal_protocol.json").read_text())
        c = self.config
        band = butter(c["butterworth_order"], c["bandpass_hz"], btype="bandpass",
                      fs=c["sample_rate_hz"], output="sos")
        self.sos = np.vstack((tf2sos(*iirnotch(c["notch_hz"], c["notch_q"], c["sample_rate_hz"])), band))
        rng = np.random.default_rng(123)
        self.raw = rng.normal(0, .5, (1800, 8))
        t = np.arange(len(self.raw)) / c["sample_rate_hz"]
        self.raw[:, 6] += 20 * np.sin(2 * np.pi * 12 * t)
        self.raw[:, 7] += 20 * np.cos(2 * np.pi * 12 * t)

    def stream(self):
        return SSVEPStream(self.config, self.sos)

    def test_chunk_invariance(self):
        whole = self.stream()
        expected = whole.push(self.raw, 0)
        expected_filtered = whole.last_filtered
        for step in (1, 10, 37, 500):
            stream = self.stream()
            events, filtered = [], []
            for i in range(0, len(self.raw), step):
                events.extend(stream.push(self.raw[i:i+step], i))
                filtered.append(stream.last_filtered)
            np.testing.assert_allclose(np.concatenate(filtered), expected_filtered, atol=1e-10)
            self.assertEqual([e["window_end_index_exclusive"] for e in events],
                             [e["window_end_index_exclusive"] for e in expected])
            np.testing.assert_allclose([e["scores"] for e in events], [e["scores"] for e in expected], atol=1e-10)
        self.assertEqual(expected[0]["window_start_index"], 160)
        self.assertEqual(expected[0]["window_end_index_exclusive"], 660)
        self.assertTrue(all(e["target_index"] == 2 and not e["control_enabled"] for e in expected))

    def test_no_future_sample_use(self):
        a, b = self.stream(), self.stream()
        changed = self.raw.copy()
        changed[660:] = 1e6
        first = a.push(self.raw, 0)[0]
        other = b.push(changed, 0)[0]
        np.testing.assert_allclose(first["scores"], other["scores"], atol=1e-10)

    def test_gap_clears_old_result_and_rewarms(self):
        s = self.stream()
        s.push(self.raw[:700], 0)
        self.assertIsNotNone(s.latest)
        self.assertEqual(s.push(self.raw[:100], 705), [])
        self.assertIsNone(s.latest)
        self.assertEqual(s.reset_reason, "sample_discontinuity")
        self.assertEqual(s.push(self.raw[100:659], 805), [])
        e = s.push(self.raw[659:660], 1364)
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["window_start_index"], 865)

    def test_duplicate_or_reversed_index_resets(self):
        for index in (695, 0):
            s = self.stream()
            s.push(self.raw[:700], 0)
            s.push(self.raw[:10], index)
            self.assertIsNone(s.latest)
            self.assertEqual(s.seen, 10)

    def test_explicit_disconnect_and_nan_reset(self):
        s = self.stream()
        s.push(self.raw[:700], 0)
        s.disconnect()
        self.assertIsNone(s.latest)
        self.assertEqual(s.status, "no_data")
        corrupt = self.raw[:10].copy()
        corrupt[2, 6] = np.nan
        self.assertEqual(s.push(corrupt, 0), [])
        self.assertEqual(s.status, "signal_invalid")
        self.assertIsNone(s.latest)

    def test_unused_channels_do_not_enter_model(self):
        a, b = self.stream(), self.stream()
        altered = self.raw.copy()
        altered[:, :6] = np.nan
        np.testing.assert_allclose([e["scores"] for e in a.push(self.raw, 0)],
                                   [e["scores"] for e in b.push(altered, 0)])

    def test_flat_or_rank_deficient_rejected(self):
        for raw in (np.zeros((700, 8)), np.ones((700, 8))):
            result = self.stream().push(raw, 0)[0]
            self.assertEqual(result["status"], "signal_invalid")
            self.assertIsNone(result["frequency_hz"])

    def test_rank2_solver_matches_cached_svd(self):
        baseline = self.stream().push(self.raw, 0)
        previous = os.environ.get('GUARDIANLOOP_EXPERIMENTAL_RANK2_CCA')
        os.environ['GUARDIANLOOP_EXPERIMENTAL_RANK2_CCA'] = '1'
        try:
            candidate = self.stream().push(self.raw, 0)
        finally:
            if previous is None:
                os.environ.pop('GUARDIANLOOP_EXPERIMENTAL_RANK2_CCA', None)
            else:
                os.environ['GUARDIANLOOP_EXPERIMENTAL_RANK2_CCA'] = previous
        self.assertEqual([e['target_index'] for e in baseline],
                         [e['target_index'] for e in candidate])
        np.testing.assert_allclose([e['scores'] for e in baseline],
                                   [e['scores'] for e in candidate], atol=1e-12)


if __name__ == "__main__":
    unittest.main()

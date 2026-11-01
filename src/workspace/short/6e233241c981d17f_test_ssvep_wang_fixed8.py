"""Protocol/identity checks; no held-out EEG is needed for these tests."""

import json
import unittest

import numpy as np

from ssvep_wang_fixed8 import PROTOCOL, _filter_window, _rows_for_subject


class WangFixedEightTest(unittest.TestCase):
    def setUp(self):
        self.protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))

    def test_montages_are_exact_fixed_sites(self):
        p = self.protocol
        self.assertEqual(p["channel_order"], ["F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2"])
        self.assertEqual(p["channel_indices_zero_based"], [7, 11, 25, 29, 23, 31, 60, 62])
        self.assertEqual(p["montages"]["O1_O2"], [6, 7])
        self.assertEqual(p["montages"]["fixed_eight"], list(range(8)))
        self.assertTrue(set(p["pilot_format_subjects_not_scored"]).isdisjoint(
            p["evaluation_subjects_predeclared"]))

    def test_window_ends_before_later_signal(self):
        p = self.protocol
        trials = np.zeros((2, 8, 1500))
        first = _filter_window(trials, 1, p)
        trials[:, :, 411:] = 1000000.0  # 1 s ends at sample 410.
        second = _filter_window(trials, 1, p)
        np.testing.assert_array_equal(first, second)

    def test_same_trials_and_truth_for_both_montages(self):
        p = self.protocol
        fs = p["sample_rate_hz"]
        frequencies = np.arange(40) / 5 + 8.0
        times = np.arange(1500) / fs
        trials = np.zeros((240, 8, 1500))
        for trial in range(240):
            trials[trial, :, :] = np.sin(2 * np.pi * frequencies[trial % 40] * times)
        rows = _rows_for_subject(99, trials, frequencies, p)
        for task in ("four_spaced_targets", "all_40_targets"):
            for window in (1, 2):
                one = [(r["block"], r["target_index_1based"]) for r in rows
                       if (r["task"], r["window_s"], r["montage"]) == (task, window, "O1_O2")]
                eight = [(r["block"], r["target_index_1based"]) for r in rows
                         if (r["task"], r["window_s"], r["montage"]) == (task, window, "fixed_eight")]
                self.assertEqual(one, eight)
                self.assertEqual(len(one), 24 if task == "four_spaced_targets" else 240)


if __name__ == "__main__":
    unittest.main()

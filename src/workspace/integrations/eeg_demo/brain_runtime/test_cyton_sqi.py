import unittest

import numpy as np

from cyton_sqi import CausalEEGFilter, CytonSQIMonitor, channel_sqi


class CytonSQITest(unittest.TestCase):
    def test_clean_and_flatline(self):
        rng = np.random.default_rng(7)
        t = np.arange(2000) / 250
        clean = np.stack([20 * np.sin(2 * np.pi * (8 + ch) * t) + rng.normal(0, 2, len(t))
                          for ch in range(8)], axis=1)
        monitor = CytonSQIMonitor(calibration_windows=2)
        monitor.process(clean)
        result = monitor.process(clean)
        self.assertTrue(result["calibrated"])
        self.assertEqual(result["usable_channels"], 8)
        damaged = clean.copy(); damaged[:, 6] = 0
        result = monitor.process(damaged)
        self.assertIn(7, result["bad_channels"])
        self.assertIn("flatline", result["channels"][6]["reasons"])

    def test_clipping(self):
        values = np.zeros((500, 8)); values[::2, 2] = 800
        sqi = channel_sqi(values)
        self.assertGreater(sqi[2, 3], 0.99)

    def test_single_bad_channel_does_not_block_other_calibration(self):
        t = np.arange(2000) / 250
        clean = np.stack([20 * np.sin(2 * np.pi * (8 + ch) * t)
                          for ch in range(8)], axis=1)
        clean[:, 6] = 0
        monitor = CytonSQIMonitor(calibration_windows=2)
        monitor.process(clean)
        result = monitor.process(clean)
        self.assertTrue(result["calibrated"])
        self.assertEqual(result["calibrated_channels"], 7)
        self.assertEqual(result["channels"][6]["calibration_current"], 0)
        self.assertEqual(result["usable_channels"], 7)
        self.assertIn(7, result["bad_channels"])
        self.assertEqual(result["quality"][6], 0.0)

    def test_transport_failure_does_not_calibrate(self):
        t = np.arange(2000) / 250
        clean = np.stack([20 * np.sin(2 * np.pi * (8 + ch) * t)
                          for ch in range(8)], axis=1)
        monitor = CytonSQIMonitor(calibration_windows=1)
        result = monitor.process(clean, transport_ok=False)
        self.assertFalse(result["calibrated"])

    def test_one_channel_transport_failure_keeps_other_references(self):
        t = np.arange(2000) / 250
        clean = np.stack([20 * np.sin(2 * np.pi * (8 + ch) * t)
                          for ch in range(8)], axis=1)
        monitor = CytonSQIMonitor(calibration_windows=1)
        result = monitor.process(clean, transport_ok=[True] * 7 + [False])
        self.assertTrue(result["calibrated"])
        self.assertEqual(result["calibrated_channels"], 7)
        self.assertEqual(result["usable_channels"], 7)
        self.assertIn("transport", result["channels"][7]["reasons"])

    def test_causal_filter_is_continuous_across_chunks(self):
        t = np.arange(3000) / 250
        values = np.stack([20 * np.sin(2 * np.pi * 10 * t) +
                           1000 * np.sin(2 * np.pi * 50 * t) for _ in range(8)], axis=1)
        whole = CausalEEGFilter().process(values)
        filt = CausalEEGFilter()
        chunked = np.concatenate((filt.process(values[:900]),
                                  filt.process(values[900:2100]),
                                  filt.process(values[2100:])))
        np.testing.assert_allclose(whole, chunked, atol=1e-8)
        self.assertLess(np.std(whole[1000:, 0]), 30)

    def test_reduced_line_noise_keeps_completed_calibration_and_quality(self):
        t = np.arange(2000) / 250
        clean = np.stack([20 * np.sin(2 * np.pi * (8 + ch) * t)
                          for ch in range(8)], axis=1)
        clean += np.random.default_rng(7).normal(0, 2, clean.shape)
        reference = clean + 4 * np.sin(2 * np.pi * 50 * t)[:, None]
        monitor = CytonSQIMonitor(calibration_windows=1)
        self.assertEqual(monitor.process(reference)['calibrated_channels'], 8)
        center, scale, threshold = (a.copy() for a in
                                   (monitor.center, monitor.scale, monitor.threshold))
        result = monitor.process(clean)
        self.assertEqual(result['usable_channels'], 8)
        self.assertEqual(result['calibrated_channels'], 8)
        for actual, expected in ((monitor.center, center), (monitor.scale, scale),
                                 (monitor.threshold, threshold)):
            np.testing.assert_array_equal(actual, expected)
        # Removing the erroneous lower-tail noise penalty must not accept
        # flat electrodes, clipping, or increased interference.
        for channel, values, reason in (
                (1, np.zeros(len(t)), 'flatline'),
                (2, 800 * np.where(np.arange(len(t)) % 2, 1, -1), 'clipping'),
                (3, clean[:, 3] + 50 * np.sin(2 * np.pi * 50 * t), 'mains')):
            damaged = clean.copy(); damaged[:, channel] = values
            status = monitor.process(damaged)['channels'][channel]
            self.assertFalse(status['usable'])
            self.assertIn(reason, status['reasons'])


if __name__ == "__main__":
    unittest.main()

"""Numerical parity checks for the deployed six-channel model path."""

import sys
import unittest
from pathlib import Path

import numpy as np
from scipy import signal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "eeg_apps_z15"))

from cyton_covariance import BANDS, CHANNELS, CovarianceFeatureStream, CovarianceSVM
from cyton_sqi import CausalEEGFilter
from gameemo_covariance_experiment import log_covariance


class CovarianceTests(unittest.TestCase):
    def test_array_buffer_matches_deque_across_wraps_and_large_chunks(self):
        cap=("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
        streams=[CovarianceFeatureStream(cap,storage=s) for s in ("deque","array")]
        rng=np.random.default_rng(41)
        model=CovarianceSVM(HERE / "gameemo_covariance_svm.npz")
        for count in (1, 10, 125, 3000, 73, 6001, 500, 2999):
            values=rng.normal(size=(count,8))*12
            for stream in streams:
                stream.append(values)
            self.assertEqual(streams[0].ready,streams[1].ready)
            if not streams[0].ready:
                with self.assertRaisesRegex(ValueError,'12 seconds'):
                    streams[1].feature()
                continue
            expected,actual=(s.feature() for s in streams)
            np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-9)
            left,right=(model.predict_feature(f) for f in (expected,actual))
            self.assertEqual(left[:2],right[:2])
            np.testing.assert_allclose(left[2],right[2],rtol=0,atol=1e-9)

    def test_array_buffer_fresh_instance_and_bad_input(self):
        cap=("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
        stream=CovarianceFeatureStream(cap,storage='array')
        self.assertFalse(stream.ready)
        stream.append(np.empty((0,8)))
        self.assertFalse(stream.ready)
        with self.assertRaisesRegex(ValueError,'finite'):
            stream.append(np.full((10,8),np.nan))
        with self.assertRaisesRegex(ValueError,'unknown covariance storage'):
            CovarianceFeatureStream(cap,storage='unknown')

    def test_stream_matches_training_feature_order(self):
        rng = np.random.default_rng(123)
        raw = rng.normal(size=(4200, 8)) * 12
        raw[:, 6] += 2 * np.sin(2 * np.pi * 10 * np.arange(len(raw)) / 250)
        conditioned = CausalEEGFilter().process(raw)
        stream = CovarianceFeatureStream(("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2"))
        for chunk in np.array_split(conditioned, 37):
            stream.append(chunk)
        filters = [signal.butter(4, band, fs=250, btype="bandpass", output="sos")
                   for band in BANDS]
        indexes = [0, 1, 4, 5, 6, 7]
        expected = np.concatenate([
            log_covariance(signal.sosfilt(sos, conditioned, axis=0)[-3000:, indexes])
            for sos in filters])
        np.testing.assert_allclose(stream.feature(), expected, rtol=0, atol=1e-9)
        self.assertEqual(CHANNELS, ("F3", "F4", "T7", "T8", "O1", "O2"))

    def test_numpy_svm_matches_sklearn(self):
        import joblib
        from sklearn.pipeline import Pipeline

        source = HERE.parent / "eeg_apps_z15" / "output" / "gameemo_covariance_v1"
        model = CovarianceSVM(HERE / "gameemo_covariance_svm.npz")
        reference = joblib.load(source / "six_channel_covariance_svm.joblib")
        self.assertIsInstance(reference, Pipeline)
        with np.load(source / "covariance_12s.npz") as cache:
            features = cache["six_shared"]
        actual = np.array([model.predict_feature(feature)[0] for feature in features])
        np.testing.assert_array_equal(actual, reference.predict(features))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from test_training import dataset
from z20_compute.data_tools import prepare_dataset, calibrate_points
from z20_compute.protocol import CHANNELS


class DataToolTests(unittest.TestCase):
    def test_eeg_manifest_runs_original_preprocessing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rng = np.random.default_rng(11)
            t = np.arange(144*250)/250
            raw = np.stack([12*np.sin(2*np.pi*(7+i*.7)*t)+rng.normal(0, 2, len(t))
                            for i in range(8)], axis=1)
            np.savez(root/"raw.npz", sample_rate_hz=250, channels=CHANNELS, samples_uv=raw)
            for split in ("train", "validation", "test"):
                np.save(root/(split+"-features.npy"), np.zeros((1, 20)))
            records = [dict(path="raw.npz" if split == "train" and label == 0 else split+"-features.npy",
                            kind="eeg" if split == "train" and label == 0 else "features",
                            label=label, group=split, split=split)
                       for split in ("train", "validation", "test") for label in range(3)]
            path = root/"manifest.json"
            path.write_text(json.dumps(dict(task="fatigue", source="synthetic integration fixture",
                                           source_kind="synthetic", records=records)))
            prepared = prepare_dataset(path)
            self.assertEqual(prepared.x.shape[1], 20)
            self.assertGreater(len(prepared.x), 9)

    def test_same_recording_path_cannot_cross_splits_under_different_group_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.save(root/"same.npy", np.zeros((1, 20)))
            records = [dict(path="same.npy", kind="features", label=label, group=split, split=split)
                       for split in ("train", "validation", "test") for label in range(3)]
            path = root/"manifest.json"
            path.write_text(json.dumps(dict(task="fatigue", source="leak fixture", source_kind="synthetic", records=records)))
            with self.assertRaisesRegex(ValueError, "across splits"):
                prepare_dataset(path)

    def test_feature_manifest_preserves_session_splits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = dataset()
            records = []
            for split in ("train", "validation", "test"):
                for label in range(3):
                    name = f"{split}-{label}.npy"
                    np.save(root/name, data.x[(data.splits == split) & (data.y == label)])
                    records.append(dict(path=name, kind="features", label=label,
                                        group=split, split=split))
            path = root/"manifest.json"
            path.write_text(json.dumps(dict(task="fatigue", source="test features",
                                           source_kind="synthetic", records=records)))
            prepared = prepare_dataset(path)
            self.assertEqual(prepared.x.shape, (180, 20))
            self.assertEqual(prepared.groups[0], "train")
            prepared.validate("fatigue")

    def test_stereo_calibration_recovers_known_baseline_in_metres(self):
        obj = np.zeros((8*6, 3), np.float32)
        obj[:, :2] = np.mgrid[0:8, 0:6].T.reshape(-1, 2)*.025
        k = np.array([[280., 0, 160], [0, 280, 120], [0, 0, 1.]])
        objects, left, right = [], [], []
        rng = np.random.default_rng(3)
        for _ in range(16):
            rvec = rng.uniform(-.35, .35, 3)
            tvec = rng.uniform([-.15, -.1, .55], [.0, .0, .9])
            objects.append(obj)
            left.append(cv2.projectPoints(obj, rvec, tvec, k, np.zeros(5))[0])
            right.append(cv2.projectPoints(obj, rvec, tvec+[-.08, 0, 0], k, np.zeros(5))[0])
        calibration, report = calibrate_points(objects, left, right, (320, 240), "test")
        self.assertAlmostEqual(float(np.linalg.norm(calibration.T)), .08, places=3)
        self.assertLess(report["stereo_rms_px"], .01)
        self.assertLess(report["rectified_vertical_error_px"], .01)


if __name__ == "__main__": unittest.main()

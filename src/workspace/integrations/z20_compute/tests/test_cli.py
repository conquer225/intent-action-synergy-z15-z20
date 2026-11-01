import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from scipy.io import wavfile
from test_training import dataset
from z20_compute.stereo import Calibration

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        process = subprocess.run([sys.executable, "-m", "z20_compute", *map(str, args)],
                                 env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr+process.stdout)
        return json.loads(process.stdout)

    def test_audio_exports_both_modes_and_known_pose_fusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tone = np.rint(.4*32767*np.sin(2*np.pi*1000*np.arange(16000)/16000)).astype(np.int16)
            wavfile.write(root/"tone.wav", 16000, tone)
            report = self.run_cli("audio", "--wav", root/"tone.wav", "--output", root/"audio", "--filtered")
            self.assertEqual(report["peak_hz"], 1000.)
            with np.load(root/"audio/audio.npz") as data:
                self.assertEqual(len(data["audio_codes"]), 16000)
                self.assertEqual(len(data["spectrum_codes"]), 513)
                self.assertEqual(data["spectrum_sync"].sum(), 1)
            xyz = np.array([[[0., 0., 1.], [.1, 0, 1.]]])
            np.savez(root/"a.npz", xyz=xyz, valid_mask=np.ones((1, 2), bool))
            pose = np.eye(4); pose[0, 3] = .2
            np.savez(root/"b.npz", xyz=xyz-[.2, 0, 0], valid_mask=np.ones((1, 2), bool))
            manifest = dict(views=[dict(depth_npz="a.npz", camera_to_world=np.eye(4).tolist()),
                                   dict(depth_npz="b.npz", camera_to_world=pose.tolist())])
            (root/"clouds.json").write_text(json.dumps(manifest))
            report = self.run_cli("fuse", "--manifest", root/"clouds.json", "--output", root/"fused")
            self.assertEqual(report["points"], 2)
            self.assertEqual(report["units"], "m")

    def test_train_and_local_depth_are_executable_without_a_board(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset().save(root/"data.npz")
            result = self.run_cli("train", "--task", "fatigue", "--dataset", root/"data.npz",
                                  "--output", root/"model", "--epochs", 20)
            self.assertFalse(result["deployable"])
            self.assertTrue((root/"model"/"metrics.json").is_file())
            k = np.array([[100., 0, 160], [0, 100, 120], [0, 0, 1.]])
            Calibration((320, 240), k, np.zeros(5), k, np.zeros(5), np.eye(3),
                        [-.1, 0, 0], "test").save(root/"calibration.json")
            left = np.random.default_rng(9).integers(0, 256, (240, 320), dtype=np.uint8)
            right = np.roll(left, -10, axis=1)
            cv2.imwrite(str(root/"left.png"), left)
            cv2.imwrite(str(root/"right.png"), right)
            depth = self.run_cli("depth", "--calibration", root/"calibration.json",
                                 "--capture-mode", "test", "--left", root/"left.png",
                                 "--right", root/"right.png", "--output", root/"depth")
            self.assertAlmostEqual(depth["distance_m"], 1., places=2)
            self.assertGreater(depth["valid_pixels"], 1000)
            self.assertTrue((root/"depth"/"cloud.ply").is_file())


if __name__ == "__main__": unittest.main()

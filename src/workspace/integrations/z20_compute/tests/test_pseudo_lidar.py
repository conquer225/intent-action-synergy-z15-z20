import io
import struct
import subprocess
import sys
import tempfile
import unittest

import cv2
import numpy as np

from pathlib import Path
from z20_compute.pseudo_lidar import (LatestPair, board_ssh_command, decode_pairs,
                                      estimate_nominal_rig, save_preview, invalidate_preview,
                                      assess_nominal_geometry)


class PseudoLidarTests(unittest.TestCase):
    def test_planar_pair_reports_geometric_ambiguity(self):
        from z20_compute.stereo_nominal import fit_nominal_rig
        points = np.array([[x, y] for y in (50., 120., 190.)
                           for x in (60., 120., 180., 240.)])
        other = points + [16., 0.]
        rig = fit_nominal_rig(points, other, (320, 240), focal_px=160.)
        quality = assess_nominal_geometry(points, other, rig)
        self.assertEqual(quality['geometry_status'], 'weak_single_pair')
        self.assertIn('predominantly_planar_matches', quality['warnings'])
        self.assertAlmostEqual(quality['homography_inlier_ratio'], 1.)

    def test_decode_board_jpeg_pairs_and_reject_bad_shape(self):
        image = np.full((240, 640, 3), 80, np.uint8)
        ok, encoded = cv2.imencode('.jpg', image)
        self.assertTrue(ok)
        payload = encoded.tobytes()
        stream = io.BytesIO(struct.pack('>II', 17, len(payload)) + payload)
        sequence, left, right = next(decode_pairs(stream))
        self.assertEqual(sequence, 17)
        self.assertEqual(left.shape, (240, 320, 3))
        self.assertEqual(right.shape, left.shape)
        with self.assertRaises(ValueError):
            list(decode_pairs(io.BytesIO(struct.pack('>II', 1, 0))))
        with self.assertRaises(ValueError):
            list(decode_pairs(io.BytesIO(struct.pack('>II', 1, len(payload)) + payload[:-2])))

    def test_latest_pair_skips_old_frames_and_rejects_regression(self):
        latest = LatestPair()
        image = np.zeros((2, 2, 3), np.uint8)
        latest.offer(3, image, image)
        latest.offer(4, image, image)
        latest.offer(2, image, image)
        self.assertEqual(latest.take(timeout=0.01)[0], 4)
        self.assertIsNone(latest.take(timeout=0.01))

    def test_invalid_result_clears_latest_valid_state(self):
        with tempfile.TemporaryDirectory() as directory:
            record = invalidate_preview(19, directory, 'insufficient texture')
            self.assertFalse(record['valid'])
            self.assertEqual(record['points'], 0)
            saved = __import__('json').loads((Path(directory) / 'latest.json').read_text())
            self.assertFalse(saved['valid'])
            self.assertNotIn('cloud', saved)

    def test_ssh_source_is_fixed_diagnostic_command(self):
        command = board_ssh_command('192.168.1.20')
        self.assertEqual(command[:2], ['ssh', '-T'])
        self.assertIn('root@192.168.1.20', command)
        self.assertIn('jpeg_stdout.py', command[-1])
        with self.assertRaises(ValueError):
            board_ssh_command('bad host; echo injected')

    def test_real_recorded_scene_estimates_nonmetric_rig(self):
        source = Path(__file__).resolve().parents[1] / 'build/navigator/scene-bgr.npy'
        if not source.exists():
            self.skipTest('recorded board pair unavailable')
        image = np.load(source, allow_pickle=False)
        left, right = (cv2.resize(half, (640, 480))
                       for half in (image[:, :640], image[:, 640:]))
        rig, quality = estimate_nominal_rig(left, right, focal_px=600)
        self.assertFalse(rig.metric)
        self.assertGreaterEqual(quality['fundamental_inliers'], 12)
        self.assertGreaterEqual(int(rig.valid_mask.sum()), 12)
        with tempfile.TemporaryDirectory() as directory:
            record = save_preview(17, left, right, rig, directory)
            self.assertFalse(record['metric'])
            self.assertGreater(record['points'], 100)
            self.assertIn('units baseline_lengths; NOT metres',
                          (Path(directory) / record['cloud']).read_text(encoding='ascii')[:300])

    def test_recorded_board_pair_runs_through_live_jpeg_protocol(self):
        source = Path(__file__).resolve().parents[1] / 'build/navigator/scene-bgr.npy'
        if not source.exists():
            self.skipTest('recorded board pair unavailable')
        image = np.load(source, allow_pickle=False)
        halves = [cv2.resize(half, (320, 240))
                  for half in (image[:, :640], image[:, 640:])]
        ok, encoded = cv2.imencode('.jpg', np.concatenate(halves, axis=1),
                                   [cv2.IMWRITE_JPEG_QUALITY, 70])
        self.assertTrue(ok)
        packet = struct.pack('>II', 123, len(encoded)) + encoded.tobytes()
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-m', 'z20_compute.pseudo_lidar',
                                     '--stdin-jpeg', '--output', directory], input=packet,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            record = __import__('json').loads(result.stdout)
            self.assertEqual(record['sequence'], 123)
            self.assertGreater(record['points'], 1000)
            self.assertFalse(record['metric'])
            self.assertTrue((Path(directory) / record['cloud']).is_file())


if __name__ == '__main__':
    unittest.main()

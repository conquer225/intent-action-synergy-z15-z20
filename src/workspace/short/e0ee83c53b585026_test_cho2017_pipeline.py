import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from cho2017_data import annotation_flags, verified_file, hashes, fetch_ranges
from cho2017_features import trial_covariances
from mi_spatial_development import BANDS, METHODS


class ChoPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads((Path(__file__).parent / 'cho2017_protocol.json').read_text())

    def setUp(self):
        rng = np.random.default_rng(20261001)
        self.samples = rng.normal(size=(3584, 8)) * 20

    def test_subject_splits_are_complete_disjoint_and_pilot_is_train(self):
        groups = [set(self.protocol[key]) for key in ('train_subjects', 'development_subjects', 'confirmation_subjects')]
        self.assertEqual([len(g) for g in groups], [30, 10, 12])
        self.assertEqual(set.union(*groups), set(range(1, 53)))
        for first, second in ((0, 1), (0, 2), (1, 2)):
            self.assertFalse(groups[first] & groups[second])
        self.assertIn(1, groups[0])

    def test_protocol_band_indices_match_reused_classifiers(self):
        self.assertEqual(self.protocol['bands_hz'], [list(band) for band in BANDS])
        for method, bands in self.protocol['band_indices'].items():
            self.assertEqual(bands, METHODS[method][0])

    def test_later_samples_cannot_change_task_feature(self):
        actual = trial_covariances(self.samples, 1023, self.protocol)
        changed = self.samples.copy()
        changed[2308:] += 50000
        np.testing.assert_array_equal(actual, trial_covariances(changed, 1023, self.protocol))
        self.assertEqual(actual.shape, (7, 8, 8))
        np.testing.assert_allclose(np.trace(actual, axis1=1, axis2=2), 1)

    def test_independent_epochs_do_not_share_filter_state(self):
        expected = trial_covariances(self.samples, 1023, self.protocol)
        trial_covariances(self.samples * 100, 1023, self.protocol)
        np.testing.assert_array_equal(expected, trial_covariances(self.samples, 1023, self.protocol))

    def test_dc_offsets_and_instantaneous_common_signal_removed(self):
        expected = trial_covariances(self.samples, 1023, self.protocol)
        common = np.sin(np.arange(3584) / 10)[:, None] * 100
        changed = self.samples + np.arange(8)[None] * 30000 + common
        np.testing.assert_allclose(expected, trial_covariances(changed, 1023, self.protocol), atol=1e-10)

    def test_one_based_bad_annotations_preserved(self):
        entries = np.empty(2, dtype=object)
        entries[0], entries[1] = np.array([1, 3]), np.array([2])
        eeg = SimpleNamespace(bad_trial_indices=SimpleNamespace(bad_trial_idx_mi=entries))
        np.testing.assert_array_equal(annotation_flags(eeg, 'bad_trial_idx_mi', 3),
                                      [True, False, True, False, True, False])
        entries[0] = np.array([0])
        with self.assertRaises(ValueError):
            annotation_flags(eeg, 'bad_trial_idx_mi', 3)

    def test_download_verification_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.bin'
            content = b'Cho source verification fixture'
            path.write_bytes(content)
            source = {'bytes': len(content), 'etag': hashlib.md5(content).hexdigest()}
            self.assertTrue(verified_file(path, source)['download_verified'])
            with self.assertRaises(ValueError):
                verified_file(path, {**source, 'etag': '0' * 32})

    def test_multipart_checksum_is_not_plain_md5(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'parts.bin'
            content = b'a' * (5 * 1024 * 1024) + b'b' * 32
            path.write_bytes(content)
            part_digest = hashlib.md5(content[:5 * 1024 * 1024]).digest() + hashlib.md5(content[5 * 1024 * 1024:]).digest()
            etag = hashlib.md5(part_digest).hexdigest() + '-2'
            self.assertEqual(hashes(path)['multipart_5MiB_etag'], etag)
            self.assertTrue(verified_file(path, {'bytes': len(content), 'etag': etag})['download_verified'])

    def test_range_transfer_refuses_external_partial_append(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.mat.part'
            path.write_bytes(b'old')

            class Response:
                status = 206
                headers = {'Content-Range': 'bytes 3-5/6', 'ETag': 'fixture'}

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    with path.open('ab') as stream:
                        stream.write(b'external')
                    return b'new'

            with patch('cho2017_data.urllib.request.urlopen', return_value=Response()):
                with self.assertRaisesRegex(ValueError, 'changed outside'):
                    fetch_ranges(path, {'url': 'https://example.test/raw', 'bytes': 6, 'etag': 'fixture'})
            self.assertEqual(path.read_bytes(), b'oldexternal')


if __name__ == '__main__':
    unittest.main()

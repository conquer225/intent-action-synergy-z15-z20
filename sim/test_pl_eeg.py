"""Sliding-window EEG behavior, independent of board transport."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/workspace/integrations'))
from pl_accel.eeg import EEGModel, EEGReference


def identity_model(window=4, hop=2):
    sos = np.zeros((3, 2, 5), dtype=np.int32)
    sos[:, :, 0] = 1 << 28
    csp = np.zeros((3, 2, 8), dtype=np.int32)
    csp[:, 0, 2] = 1 << 14
    csp[:, 1, 3] = 1 << 14
    return EEGModel(sos, csp, [-4096, 4096, 0, 0, 0, 0], 0, window=window, hop=hop)


class EEGBehavior(unittest.TestCase):
    def test_csp_log_variance_and_svm_worked_example(self):
        samples = np.zeros((4, 8), dtype=np.int32)
        samples[:, 2] = [256, -256, 256, -256]
        samples[:, 3] = [512, -512, 512, -512]
        engine = EEGReference(identity_model())
        result = engine.feed(samples)[0]
        self.assertEqual(result['features'][1] - result['features'][0], 8192)
        self.assertEqual(result['score_q24'], 33554432)
        self.assertEqual(result['label'], 'right')
        self.assertTrue(result['valid'])

    def test_sliding_windows_use_only_new_samples_and_reset(self):
        samples = np.zeros((6, 8), dtype=np.int32)
        samples[:, 2] = [256, -256] * 3
        samples[:, 3] = [512, -512] * 3
        engine = EEGReference(identity_model())
        self.assertEqual(engine.feed(samples[:3]), [])
        self.assertEqual([r['sample_count'] for r in engine.feed(samples[3:])], [4, 6])
        engine.reset()
        self.assertEqual(engine.feed(samples[:3]), [])

    def test_silence_has_no_valid_classification(self):
        result = EEGReference(identity_model()).feed(np.zeros((4, 8), np.int32))[0]
        self.assertFalse(result['valid'])
        self.assertIsNone(result['label'])

    def test_model_round_trip_and_rejects_incompatible_channels(self):
        model = identity_model()
        restored = EEGModel.from_dict(model.to_dict())
        np.testing.assert_array_equal(restored.parameter_words(), model.parameter_words())
        data = model.to_dict()
        data['channels'][2] = 'OTHER'
        with self.assertRaises(ValueError):
            EEGModel.from_dict(data)


if __name__ == '__main__':
    unittest.main()

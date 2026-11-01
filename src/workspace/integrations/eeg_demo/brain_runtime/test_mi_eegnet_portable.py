import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from mi_eegnet_portable import OfflineEEGNet
from mi_features import CHANNELS


def fixture(path, **metadata_changes):
    metadata = dict(channels=list(CHANNELS), window_samples=500, sample_rate_hz=250,
                    status='offline_plumbing_only', control_enabled=False,
                    promotion_gate_passed=False, production_eligible=False,
                    config=dict(F1=8,D=2,F2=16,temporal_kernel=128,separable_kernel=16,
                                pools=[4,8],bn_eps=.001))
    metadata.update(metadata_changes)
    data = {'temporal.weight':np.zeros((8,1,1,128)), 'block1.1.weight':np.zeros((16,1,8,1)),
            'block2.1.weight':np.zeros((16,1,1,16)), 'block2.2.weight':np.zeros((16,16,1,1)),
            'dense.weight':np.zeros((2,240)), 'dense.bias':np.array([1.,2.]),
            'source_mean':np.zeros(8), 'source_scale':np.ones(8),
            'metadata':json.dumps(metadata)}
    for prefix, width in (('block1.0',8),('block1.2',16),('block2.3',16)):
        for key in ('weight','bias','running_mean','running_var'):
            data[prefix+'.'+key] = np.ones(width) if key in ('weight','running_var') else np.zeros(width)
    np.savez(path, **data)


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)/'test.npz'
        fixture(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_default_refuses_experimental_artifact(self):
        with self.assertRaises(ValueError):
            OfflineEEGNet(self.path)

    def test_pipeline_keeps_bias_and_class_order(self):
        model = OfflineEEGNet(self.path, allow_experimental=True)
        np.testing.assert_array_equal(model.logits(np.ones((2,8,500))), [[1,2],[1,2]])

    def test_shape_and_finite_checks(self):
        model = OfflineEEGNet(self.path, allow_experimental=True)
        for values in (np.ones((8,500)),np.ones((1,8,750)),np.empty((0,8,500)),
                       np.full((1,8,500),np.nan)):
            with self.assertRaises(ValueError):
                model.logits(values)

    def test_never_accepts_production_flags_or_wrong_channels(self):
        for fields in (dict(control_enabled=True),dict(production_eligible=True),
                       dict(promotion_gate_passed=True),dict(channels=list(reversed(CHANNELS)))):
            fixture(self.path, **fields)
            with self.assertRaises(ValueError):
                OfflineEEGNet(self.path, allow_experimental=True)

    def test_negative_bn_variance_refused(self):
        with np.load(self.path,allow_pickle=False) as saved:
            data = {key:saved[key] for key in saved.files}
        data['block1.0.running_var'] = -np.ones(8)
        np.savez(self.path, **data)
        with self.assertRaises(ValueError):
            OfflineEEGNet(self.path, allow_experimental=True)


if __name__ == '__main__':
    unittest.main()

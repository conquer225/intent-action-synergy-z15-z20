"""Candidate-only runtime tests; the production loader remains unchanged."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pynq_guardianloop'))
from mi_eegnet_portable import OfflineEEGNet
from mi_window_rms import TRANSFORM_ID
from test_mi_eegnet_portable import fixture

runtime=ROOT/'eeg_apps_z15/output/mi_rms_runtime_20261003/mi_eegnet_portable.py'
spec=importlib.util.spec_from_file_location('rms_portable_tests',runtime)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RMSPortableTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.path=Path(self.directory.name)/'candidate.npz'
        fixture(self.path,status='offline_shared_rms_only',input_transform=TRANSFORM_ID)
        with np.load(self.path,allow_pickle=False) as data:
            values={key:data[key].copy() for key in data.files}
        rng=np.random.default_rng(42)
        for key in ('temporal.weight','block1.1.weight','block2.1.weight','block2.2.weight','dense.weight'):
            values[key]=rng.normal(scale=.1,size=values[key].shape)
        np.savez(self.path,**values)
        self.waves=rng.normal(size=(2,8,500))

    def tearDown(self): self.directory.cleanup()

    def test_old_loader_refuses_candidate(self):
        with self.assertRaises(ValueError): OfflineEEGNet(self.path,allow_experimental=True)

    def test_new_loader_requires_explicit_transform(self):
        with np.load(self.path,allow_pickle=False) as data:
            values={key:data[key].copy() for key in data.files}
        meta=json.loads(str(values['metadata'].item()))
        del meta['input_transform']
        values['metadata']=json.dumps(meta)
        np.savez(self.path,**values)
        with self.assertRaises(ValueError): module.OfflineEEGNet(self.path,allow_experimental=True)

    def test_new_loader_refuses_unapproved_use(self):
        with self.assertRaises(ValueError): module.OfflineEEGNet(self.path)

    def test_gain_invariance_with_nonzero_network(self):
        model=module.OfflineEEGNet(self.path,allow_experimental=True)
        expected=model.logits(self.waves)
        self.assertGreater(np.max(np.abs(expected-[1,2])),1e-6)
        for gain in (.03125,.125,2,32):
            np.testing.assert_array_equal(model.logits(self.waves*gain),expected)

    def test_flat_input_refused_before_network(self):
        model=module.OfflineEEGNet(self.path,allow_experimental=True)
        with self.assertRaises(ValueError): model.logits(np.zeros((1,8,500)))


if __name__=='__main__': unittest.main()

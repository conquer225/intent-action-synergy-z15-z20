import importlib.util
import os
import sys
from pathlib import Path
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'brain_runtime'))
from cyton_covariance import CovarianceSVM, CovarianceFeatureStream
from cyton_fatigue import FourChannelFatigue


def original(name):
    base=Path(os.environ.get('GL_BASELINE_ROOT',str(ROOT.parent/'guardianloop_team_20261017_03')))
    if not base.exists():base=ROOT.parent
    path = base/'latest_saved_runtime/rootfs/home/xilinx/jupyter_notebooks/guardianloop_pynq'/(name+'.py')
    spec = importlib.util.spec_from_file_location('reference_'+name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class ProcessingTests(unittest.TestCase):
    def test_emotion_reuses_exact_feature_once_and_predictions_match_original(self):
        class Stream:
            ready = True
            def __init__(self): self.calls = 0
            def feature(self): self.calls += 1; return np.arange(105, dtype=float)/20
        path = ROOT/'brain_runtime/gameemo_covariance_svm.npz'
        model = CovarianceSVM(path); reference = original('cyton_covariance').CovarianceSVM(path)
        stream = Stream()
        self.assertEqual(model.predict(stream, [1.]*6), reference.predict(Stream(), [1.]*6))
        self.assertEqual(stream.calls, 1)
        self.assertEqual(model.diagnostics['values'], (np.arange(105)/20).tolist())
        self.assertEqual(model.diagnostics['shape'], [5,21])
        model.predict(stream, [0.]*6)
        self.assertIsNone(model.diagnostics)

    def test_fatigue_diagnostics_leave_all_calibration_and_predictions_unchanged(self):
        path = ROOT/'brain_runtime/cyton_fatigue_overlap4.json'
        model = FourChannelFatigue(path); reference = original('cyton_fatigue').FourChannelFatigue(path)
        rng = np.random.default_rng(18)
        for index in range(17):
            values = rng.normal(0,12,(2000,8))
            for item in (model,reference): item.append(values)
            actual=model.process_window(True,True)
            self.assertEqual(actual,reference.process_window(True,True))
            np.testing.assert_array_equal(model.diagnostics['values'],model.stream.features())
        self.assertEqual(model.diagnostics['shape'],[4,5])
        model.process_window(False,True);self.assertIsNone(model.diagnostics)
        model.reset_stream();self.assertIsNone(model.diagnostics)


if __name__ == '__main__': unittest.main()

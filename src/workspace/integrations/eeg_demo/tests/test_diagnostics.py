import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'brain_runtime'))
from processing_diagnostics import processing_snapshot


class DiagnosticTests(unittest.TestCase):
    def test_window_bounds_and_features_use_actual_collected_sample_count(self):
        model=SimpleNamespace(diagnostics={'kind':'log_covariance','values':[2.]*105,'shape':[5,21]})
        fatigue=SimpleNamespace(diagnostics={'kind':'differential_entropy','values':[3.]*20,'shape':[4,5]})
        result=processing_snapshot(2500,4000,2,model,fatigue,True,True)
        self.assertEqual(result['emotion']['collected_samples'],2500)
        self.assertEqual(result['emotion']['window'],[1500,4000])
        self.assertEqual(result['fatigue']['window'],[2000,4000])
        self.assertEqual(result['emotion']['features']['values'],[2.]*105)
        self.assertEqual(result['filter']['bandpass_hz'],[1,45])
        invalid=processing_snapshot(20,4020,3,model,fatigue,False,False)
        self.assertIsNone(invalid['emotion']['features'])
        self.assertIsNone(invalid['fatigue']['features'])
        self.assertEqual(invalid['fatigue']['collected_samples'],20)

    def test_fatigue_feature_range_remains_the_last_actual_inference_window(self):
        model=SimpleNamespace(diagnostics={'values':[1.]*20})
        result=processing_snapshot(6000,7000,5,None,model,False,True,fatigue_feature_end=5500)
        self.assertEqual(result['fatigue']['window'],[5000,7000])
        self.assertEqual(result['fatigue']['feature_window'],[3500,5500])


if __name__=='__main__':unittest.main()

import time,unittest
from pathlib import Path
import numpy as np
from z20_compute.feature_runtime import FeatureRuntime
from z20_compute.training import ModelBundle,PREPROCESSORS

ROOT=Path(__file__).resolve().parents[1]


class NpuFeedbackTests(unittest.TestCase):
 def test_eeg_result_exposes_actual_input_and_comparable_computation_times(self):
  model=ModelBundle.load(ROOT/'artifacts/headless/models/emotion')
  class Backend:
   name='test_integer_backend'
   def infer(self,integer,values):
    self.last_timing=dict(total_seconds=.001,launch_to_done_seconds=.0005)
    return integer.infer(values)
  runtime=FeatureRuntime({'emotion':model},backend=Backend())
  values=np.arange(180,dtype=float)/100
  try:
   self.assertTrue(runtime.submit_local('emotion',values,feature_version=PREPROCESSORS['emotion'],window_id='input-17',source='recorded:test'))
   end=time.monotonic()+2
   while time.monotonic()<end:
    result=runtime.status()['emotion']
    if result.get('window_id')=='input-17':break
    time.sleep(.01)
   self.assertEqual(result['features'],values.tolist())
   self.assertEqual(len(result['quantized_features']),180)
   self.assertTrue(result['integer_reference_equal'])
   self.assertGreater(result['timing']['software_seconds'],0)
   self.assertGreater(result['timing']['npu_predict_seconds'],0)
   self.assertEqual(result['timing']['total_seconds'],.001)
   self.assertIn('completed_monotonic',result)
  finally:runtime.close()

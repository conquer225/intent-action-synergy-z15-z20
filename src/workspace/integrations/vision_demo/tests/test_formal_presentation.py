import unittest,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
runtime=ROOT.parent/'eeg_demo/runtime'
eye=ROOT.parents[1]/'integrations/guardianloop_team_20261017_03/projects/codex_project/brain_eye_coexist/candidate/eye'
if not eye.exists():eye=Path(os.environ.get('GL_BASELINE_ROOT',str(ROOT.parents[1])))/'projects/codex_project/brain_eye_coexist/candidate/eye'
sys.path[:0]=[str(runtime),str(eye/'src')]
from presentation_eye import Renderer
from guide import View
class CalibrationPresentationTests(unittest.TestCase):
 def test_white_calibration_target_and_original_dark_field_are_preserved(self):
  renderer=Renderer(relative=True,live=True)
  for phase in ('settle','collect','waiting'):
   image=renderer.render(View(phase=phase,point=0,remaining=2))
   self.assertEqual(tuple(image[360,650]),(242,243,241))
   self.assertEqual(tuple(image[200,1000]),(27,23,19))

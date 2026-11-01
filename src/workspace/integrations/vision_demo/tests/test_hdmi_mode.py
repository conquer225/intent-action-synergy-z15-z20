import unittest
from types import SimpleNamespace
from vision_demo.continuous import CameraStartError


class HdmiModeRecoveryTests(unittest.TestCase):
 def test_safe_camera_admission_failure_leaves_mode_and_invalidates_home_cache(self):
  from vision_demo.hdmi_mode import service_vision
  calls=[]
  def fail(now):raise CameraStartError('camera admission failed')
  vision=SimpleNamespace(service=fail,continuous=SimpleNamespace(active=False,buffers=[]),leave=lambda:calls.append('leave'))
  display=SimpleNamespace(controller=SimpleNamespace(_enter=lambda page,now:calls.append((page,now))),buffer_pages={0:7},calibration_view='old')
  self.assertEqual(service_vision(vision,display,4),'camera admission failed')
  self.assertEqual(calls,['leave',('home',4)]);self.assertEqual(display.buffer_pages,{})
  self.assertIsNone(display.calibration_view)

 def test_retained_dma_and_other_faults_are_never_converted_to_home(self):
  from vision_demo.hdmi_mode import service_vision
  for error,buffers in ((CameraStartError('unsafe'),[object()]),(RuntimeError('DMA halt failed'),[])):
   calls=[]
   def fail(now):raise error
   vision=SimpleNamespace(service=fail,continuous=SimpleNamespace(active=False,buffers=buffers),leave=lambda:calls.append('leave'))
   display=SimpleNamespace(controller=SimpleNamespace(_enter=lambda *args:calls.append('home')),buffer_pages={0:7},calibration_view='old')
   with self.assertRaises(type(error)):service_vision(vision,display,4)
   self.assertEqual(calls,[]);self.assertEqual(display.buffer_pages,{0:7})

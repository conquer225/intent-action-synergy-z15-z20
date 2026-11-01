import unittest
from vision_demo.eye_observer import observe_eye,can_enter
class EyeObservationTests(unittest.TestCase):
    def test_observation_keeps_eye_polling_and_suppresses_gaze_actions(self):
        calls=[]
        class Controller:
            def gaze(self,*args):calls.append('gaze')
            def _stop(self,*args):calls.append('stop')
        class Eye:
            def poll(self,controller,now):
                controller.gaze({},now);controller._stop(now,'lost');return 'view'
        self.assertEqual(observe_eye(Eye(),Controller(),1),'view')
        self.assertEqual(calls,['stop'])
    def test_calibration_and_verification_keep_their_screen(self):
        class Guide:phase='collect'
        class Eye:guide=Guide()
        self.assertFalse(can_enter(Eye()))
        Eye.guide.phase='selection';self.assertTrue(can_enter(Eye()))
        self.assertTrue(can_enter(None))
if __name__=='__main__':unittest.main()

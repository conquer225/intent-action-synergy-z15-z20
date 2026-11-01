import unittest
from intent_one.controls import PsControls
class Edges:
    down={0:False,1:False}
class Reader:
    mapping={0:'start',1:'pause'}
    def __init__(self):self.edges=Edges();self.edges.down={0:False,1:False};self.events=[]
    def poll(self,now):result=self.events;self.events=[];return result
class PsControlTests(unittest.TestCase):
    def test_eye_calibration_press_does_not_spawn_a_second_worker(self):
        reader=Reader();keys=PsControls(reader);reader.edges.down[0]=True;reader.events=['start']
        self.assertEqual(keys.poll(0,'eye','collect'),[])
    def test_original_eye_keys_and_brain_short_long_actions(self):
        reader=Reader();keys=PsControls(reader)
        reader.edges.down[0]=True;reader.events=['start']
        self.assertEqual(keys.poll(0,'eye','positioning'),['p'])
        reader.edges.down[0]=False;keys.poll(.1,'eye','positioning')
        reader.edges.down[0]=True;reader.events=['start'];self.assertEqual(keys.poll(1,'eeg','eeg'),[])
        reader.edges.down[0]=False;self.assertEqual(keys.poll(1.2,'eeg','eeg'),['confirm'])
        reader.edges.down[0]=True;reader.events=['start'];keys.poll(2,'eeg','mi')
        self.assertEqual(keys.poll(2.81,'eeg','mi'),['mi-left'])
        self.assertEqual(keys.poll(3,'eeg','mi'),[])
        reader.events=['pause'];self.assertEqual(keys.poll(3.1,'eeg','mi'),['pause'])
if __name__=='__main__':unittest.main()

import time,unittest
from z20_compute.visual_demo import DemoState
from z20_compute.visual_server import DemoServer,DemoClient


class ClassificationInputTests(unittest.TestCase):
 def test_external_sound_is_fenced_and_selects_sound_task(self):
  state=DemoState();state.attach_renderer()
  for i,name in enumerate(('right','right','enter'),1):state.command('test',i,name)
  with DemoServer(state,'127.0.0.1',0,0,token='test') as server, DemoClient('127.0.0.1',server.control_port,token='test') as client:
   before=state.epoch
   reply=client.sound_input([.1]*40,source='live:pc_microphone',window_id='mic-1')
   self.assertTrue(reply['accepted']);self.assertGreater(state.epoch,before)
   self.assertEqual(reply['sample_index'],2)
   self.assertEqual(state.snapshot()['sound_input']['window_id'],'mic-1')
   self.assertFalse(client.request(dict(op='sound_input',session=state.session,epoch=before,
       vector=[.9]*40,source='live:pc_microphone',window_id='old'))['accepted'])
   self.assertEqual(state.snapshot()['sound_input']['window_id'],'mic-1')


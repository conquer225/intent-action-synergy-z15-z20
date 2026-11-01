import time,unittest
from pathlib import Path


class OfflineTests(unittest.TestCase):
    def test_waiting_for_new_eeg_window_does_not_show_a_previous_prediction(self):
        import threading
        from z20_compute.visual_offline import OfflineBoard
        from z20_compute.visual_server import DemoClient
        from z20_compute.training import PREPROCESSORS
        root=Path(__file__).resolve().parents[1];entered=threading.Event();release=threading.Event()
        with OfflineBoard(root) as board:
            board.runtime.submit_local('emotion',[0.]*180,feature_version=PREPROCESSORS['emotion'],window_id='old',source='recorded:old')
            deadline=time.monotonic()+2
            while board.runtime.status()['emotion'].get('window_id')!='old' and time.monotonic()<deadline:time.sleep(.01)
            original=board.runtime.models['emotion']
            class SlowModel:
                version=original.version
                def quantize_input(self,values):return original.quantize_input(values)
                def predict(self,values,**kwargs):entered.set();release.wait(2);return original.predict(values,**kwargs)
            board.runtime.models['emotion']=SlowModel()
            try:
                with DemoClient('127.0.0.1',board.server.control_port,token=board.token,role='renderer') as renderer, DemoClient('127.0.0.1',board.server.control_port,token=board.token) as controller:
                    for name in ('right','right','enter','right'):controller.command(name)
                    self.assertTrue(entered.wait(1));time.sleep(.08)
                    trace=renderer.status()['data']['npu']
                    self.assertEqual(trace['event'],'submitted')
                    self.assertFalse(trace['valid']);self.assertIsNone(trace['scores'])
                    self.assertNotEqual(trace['window_id'],'old')
                    self.assertTrue(all(thread.is_alive() for thread in board.threads))
            finally:release.set()

    def test_offline_board_uses_real_recorded_features_and_never_claims_pl(self):
        from z20_compute.visual_offline import OfflineBoard
        from z20_compute.visual_server import DemoClient
        root=Path(__file__).resolve().parents[1]
        with OfflineBoard(root) as board:
            with DemoClient('127.0.0.1',board.server.control_port,token=board.token,role='renderer') as renderer, \
                 DemoClient('127.0.0.1',board.server.control_port,token=board.token) as controller:
                controller.command('right');controller.command('right');controller.command('enter')
                for task,dimension in (('fatigue',20),('emotion',180),('sound',40)):
                    deadline=time.monotonic()+2;trace={}
                    while time.monotonic()<deadline:
                        trace=renderer.status()['data'].get('npu',{})
                        if trace.get('task')==task and trace.get('event')=='completed':break
                        time.sleep(.01)
                    self.assertEqual(trace['backend'],'PS_integer_reference')
                    self.assertEqual(len(trace['features']),dimension)
                    self.assertTrue(trace['source'].startswith('recorded:'))
                    self.assertFalse(board.state.snapshot()['actuator_control'])
                    controller.command('right')
        self.assertFalse(any(t.is_alive() for t in board.threads))

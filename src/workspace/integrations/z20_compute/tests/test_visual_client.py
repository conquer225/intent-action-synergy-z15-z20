import threading,time,unittest
from unittest.mock import patch
from z20_compute.z15_visual_client import Z15VisualClient


class ClientTests(unittest.TestCase):
    def test_eye_action_queued_for_an_old_mode_is_discarded(self):
        blocked=threading.Event();release=threading.Event();commands=[]
        class Transport:
            session='a'*32;epoch=1
            def __init__(self,*args,**kwargs):self.calls=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def status(self):
                self.calls+=1
                if self.calls==2:
                    blocked.set();release.wait(2);self.epoch=2
                return dict(session=self.session,epoch=self.epoch,menu=True,mode='fluid')
            def command(self,name):commands.append(name);return self.status()
        with patch('z20_compute.z15_visual_client.require_wireless'),patch('z20_compute.z15_visual_client.DemoClient',Transport):
            client=Z15VisualClient('192.168.50.20','token')
            try:
                self.assertTrue(blocked.wait(2));self.assertTrue(client.send('right'));release.set()
                deadline=time.monotonic()+2
                while client.snapshot().get('epoch')!=2 and time.monotonic()<deadline:time.sleep(.01)
                self.assertEqual(client.snapshot()['epoch'],2);self.assertEqual(commands,[])
            finally:release.set();client.close()

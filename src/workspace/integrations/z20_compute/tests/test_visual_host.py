import threading,time,unittest
from unittest.mock import patch
from z20_compute.visual_demo import DemoState
from z20_compute.visual_server import DemoServer,DemoClient
from z20_compute.visual_host import VisualHost


class HostTests(unittest.TestCase):
    def test_delayed_poll_cannot_undo_acknowledged_mode(self):
        state=DemoState();blocked=threading.Event();release=threading.Event()
        observed=threading.Event();finish=threading.Event()
        class DelayedClient:
            def __init__(self,*args,role='controller',**kwargs):
                self.client=DemoClient(*args,role=role,**kwargs);self.role=role;self.calls=0
            def __enter__(self):return self
            def __exit__(self,*args):self.client.close()
            def status(self):
                result=self.client.status();self.calls+=1
                if self.role=='renderer' and self.calls==2:blocked.set();release.wait(2)
                if self.role=='renderer' and self.calls==3:observed.set();finish.wait(2)
                return result
            def command(self,name):return self.client.command(name)
        with DemoServer(state,'127.0.0.1',0,0,token='test') as server:
            with patch('z20_compute.visual_host.DemoClient',DelayedClient):
                host=VisualHost('127.0.0.1','test',control_port=server.control_port,frame_port=server.frame_port).start()
                try:
                    self.assertTrue(blocked.wait(2));self.assertTrue(host.command('right')['accepted'])
                    release.set();self.assertTrue(observed.wait(2))
                    self.assertEqual(host.snapshot()['mode'],'spectrum')
                finally:release.set();finish.set();host.close()

    def test_acknowledged_navigation_is_immediately_visible_to_caller(self):
        state=DemoState()
        with DemoServer(state,'127.0.0.1',0,0,token='test') as server:
            with DemoClient('127.0.0.1',server.control_port,token='test',role='renderer') as renderer, \
                 DemoClient('127.0.0.1',server.control_port,token='test') as controller:
                host=VisualHost('127.0.0.1','test')
                host.controller=controller;host.state=renderer.status()
                for name,expected in (('right','spectrum'),('right','npu'),('right','spatial'),('right','fluid')):
                    reply=host.command(name)
                    self.assertTrue(reply['accepted'])
                    self.assertEqual(host.snapshot()['mode'],expected)
                    self.assertEqual(host.snapshot()['epoch'],reply['epoch'])

import io
import socket
import unittest
import cv2
import numpy as np
from z20_compute.visual_demo import DemoState
from z20_compute.visual_server import DemoServer, DemoClient
from z20_compute.visual_wire import write_json, read_json, write_frame


class ServerTests(unittest.TestCase):
    def test_old_mode_and_old_session_commands_are_not_executed(self):
        state=DemoState()
        with DemoServer(state,'127.0.0.1',0,0,token='test-token') as server:
            with DemoClient('127.0.0.1',server.control_port,token='test-token') as eye:
                old=eye.status();eye.command('enter')
                result=eye.request(dict(op='command',sequence=99,name='right',session=old['session'],epoch=old['epoch']))
                self.assertFalse(result['accepted']);self.assertEqual(state.action_id,0)
                result=eye.request(dict(op='command',sequence=100,name='right',session='a'*32,epoch=state.epoch))
                self.assertFalse(result['accepted']);self.assertEqual(state.action_id,0)

    def test_authenticated_control_jpeg_and_reconnect_over_real_sockets(self):
        state=DemoState()
        with DemoServer(state,'127.0.0.1',0,0,token='test-token') as server:
            with self.assertRaises(PermissionError):
                DemoClient('127.0.0.1',server.control_port,token='wrong',role='controller')
            with DemoClient('127.0.0.1',server.control_port,token='test-token',role='renderer') as renderer:
                with DemoClient('127.0.0.1',server.control_port,token='test-token',role='controller') as eye:
                    result=eye.command('enter');self.assertFalse(result['menu'])
                    meta=renderer.status()
                    with socket.create_connection(('127.0.0.1',server.frame_port),timeout=2) as sock:
                        stream=sock.makefile('rwb');write_json(stream,dict(token='test-token',session=renderer.session));self.assertTrue(read_json(stream)['ok'])
                        _,jpeg=cv2.imencode('.jpg',np.full((180,320,3),80,np.uint8))
                        write_frame(stream,renderer.session,meta['epoch'],1,jpeg.tobytes())
                        self.assertTrue(read_json(stream)['accepted'])
                        self.assertEqual(state.latest()[1],1)
                        eye.command('back')
                        write_frame(stream,renderer.session,meta['epoch'],2,jpeg.tobytes())
                        self.assertFalse(read_json(stream)['accepted'])

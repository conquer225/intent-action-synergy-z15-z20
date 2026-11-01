import importlib.util
from pathlib import Path
import socket
import threading
import json
import unittest

PATH=Path(__file__).resolve().parents[2]/'tools/commissioning_probe.py'
spec=importlib.util.spec_from_file_location('commissioning_probe',PATH)
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def exercise(self,bad=False):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);actions=[]
        def serve():
            with listener:
                connection,_=listener.accept()
                with connection:
                    stream=connection.makefile('rb')
                    for wire in stream:
                        request=json.loads(wire);actions.append(request['action'])
                        response={'v':1,'seq':request['seq']+(100 if bad else 0),'ok':True,'status':{'pendulum':{'enabled':False}}}
                        connection.sendall(json.dumps(response).encode()+b'\n')
        thread=threading.Thread(target=serve,daemon=True);thread.start()
        result=probe.probe('127.0.0.1',listener.getsockname()[1],duration=.25)
        thread.join(1)
        return result,actions

    def test_real_socket_roundtrip_only_observes_and_matches_replies(self):
        result,actions=self.exercise()
        self.assertTrue(result['passed']);self.assertGreaterEqual(result['acks'],4)
        self.assertEqual(actions[0],'hello');self.assertIn('heartbeat',actions);self.assertIn('status',actions)
        self.assertLessEqual(set(actions),{'hello','status','heartbeat'})

    def test_other_sequence_cannot_satisfy_the_current_request(self):
        result,_=self.exercise(True)
        self.assertFalse(result['passed']);self.assertEqual(result['acks'],0)


if __name__=='__main__':unittest.main()

import socket
import threading
import time
import unittest


class ReconnectTests(unittest.TestCase):
    def test_connection_failure_drops_old_input_then_recovers_without_blocking_caller(self):
        from z20_compute.z15_client import ReconnectingFeatures
        server=socket.socket();server.bind(('127.0.0.1',0));port=server.getsockname()[1];server.close()
        client=ReconnectingFeatures('127.0.0.1',port,retry_seconds=.05)
        client.start()
        try:
            before=time.monotonic()
            self.assertFalse(client.offer_features('fatigue',[0.]*20,window_id='offline',
                source='recorded:test',feature_version='fatigue-calibrated-de20-v1'))
            self.assertLess(time.monotonic()-before,.1)
            server=socket.socket();server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            server.bind(('127.0.0.1',port));server.listen(2);server.settimeout(2)
            first,_=server.accept()
            deadline=time.monotonic()+1
            while not client.connected and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue(client.connected)
            first.close()
            second,_=server.accept()
            deadline=time.monotonic()+1
            while client.connections<2 and time.monotonic()<deadline:time.sleep(.005)
            second.close()
            self.assertGreaterEqual(client.connections,2)
            self.assertIsNone(client.result('fatigue'))
        finally:
            client.close();server.close()


if __name__=='__main__':unittest.main()

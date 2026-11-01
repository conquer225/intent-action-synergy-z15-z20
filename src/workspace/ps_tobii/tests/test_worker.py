import sys
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from calibration_worker import Worker

class WorkerTests(unittest.TestCase):
    def worker(self,code):
        w=Worker.__new__(Worker)
        w.process=Mock();w.process.poll.return_value=code
        w.buffer=bytearray();w.done=False;w.result=None
        return w
    def test_result_waits_for_successful_cleanup(self):
        w=self.worker(None)
        data=b'{"kind":"result","calibrated":true,"valid_samples":60}\n'
        with patch('calibration_worker.os.read',side_effect=[data,BlockingIOError()]):
            self.assertEqual(w.poll(),[])
        w.process.poll.return_value=0
        with patch('calibration_worker.os.read',return_value=b''):
            self.assertEqual(w.poll()[0]['valid_samples'],60)
            self.assertEqual(w.poll(),[])
    def test_cleanup_failure_cannot_publish_success(self):
        w=self.worker(1)
        with patch('calibration_worker.os.read',side_effect=[b'{"kind":"result","calibrated":true}\n',b'']):
            events=w.poll()
        self.assertEqual(events,[{'kind':'error','code':1}])
    def test_live_calibration_ready_does_not_wait_for_usb_close(self):
        w=self.worker(None)
        data=b'{"kind":"calibration_ready","calibrated":true,"valid_samples":603}\n'
        with patch('calibration_worker.os.read',side_effect=[data,BlockingIOError()]):
            self.assertEqual(w.poll()[0]['kind'],'calibration_ready')
        self.assertFalse(w.done)
        w.process.poll.return_value=1
        with patch('calibration_worker.os.read',return_value=b''):
            self.assertEqual(w.poll(),[{'kind':'error','code':1}])
    def test_fragmented_event_is_not_dispatched_early(self):
        w=self.worker(None)
        with patch('calibration_worker.os.read',side_effect=[b'{"kind":"poi',BlockingIOError()]):
            self.assertEqual(w.poll(),[])
        with patch('calibration_worker.os.read',side_effect=[b'nt","point":2,"accepted":false}\n',BlockingIOError()]):
            self.assertEqual(w.poll(),[{'kind':'point','point':2,'accepted':False}])
    def test_abort_signals_once_so_cleanup_can_finish(self):
        w=self.worker(None);w.aborted=False
        with patch('calibration_worker.os.killpg',create=True) as kill:
            w.abort();w.abort();self.assertEqual(kill.call_count,1)

if __name__=='__main__':unittest.main()

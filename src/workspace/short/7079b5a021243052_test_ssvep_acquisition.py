"""Reader-lane numeric parity and recovery; synthetic inputs, isolated files/ports."""
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

from cyton_reader_sink import decode_eeg_counts
from ssvep_acquisition import consume_packets, SSVEPReaderRuntime
from ssvep_cue_runtime import SSVEPCueBridge
from ssvep_shadow import CHANNELS, SSVEPShadow
from test_ssvep_cue_runtime import ASSETS, SOS


def packet(index):
    t = index/250
    counts = [0]*6+[round(500*np.sin(2*np.pi*12*t)+40*np.sin(2*np.pi*17*t)),
                    round(400*np.sin(2*np.pi*12*t+.3)+40*np.sin(2*np.pi*19*t))]
    return b'\xa0'+bytes((index%256,))+b''.join((c&0xffffff).to_bytes(3,'big') for c in counts)+b'\0'*6+b'\xc0'


class ConsumerTests(unittest.TestCase):
    def test_adc_decodes_signed_24_bit_boundaries(self):
        counts=[-2**23,-1,0,1,2**23-1,17,-27,4096]
        raw=b'\xa0\0'+b''.join((c&0xffffff).to_bytes(3,'big') for c in counts)+b'\0'*6+b'\xc0'
        np.testing.assert_array_equal(decode_eeg_counts(raw),counts)

    def consume(self, rows, shadow, now=100., batch_samples=1):
        stopped=threading.Event()
        pending=Mock()
        def get(timeout):
            if rows:
                return rows.pop(0)
            stopped.set()
            raise queue.Empty()
        pending.get.side_effect=get
        with patch('ssvep_acquisition.time.monotonic',lambda:now):
            consume_packets(pending,stopped,shadow,decode_eeg_counts,.022,batch_samples)

    def test_batch_keeps_per_packet_expiry_and_gap_detection(self):
        shadow=Mock(gaps=0);shadow.latest={'reason':'startup'}
        self.consume([((1,packet(0),0,99.49),(2,packet(1),0,100.),
                       (258,packet(2),0,100.))],shadow,batch_samples=10)
        self.assertEqual(shadow.packet.call_count,2)
        self.assertEqual(shadow.gaps,1)
        self.assertIn(unittest.mock.call('input_backlog',publish=True),shadow.disconnect.call_args_list)

    def test_ordinal_gap_detects_even_256_dropped_packets(self):
        shadow=Mock(gaps=0)
        self.consume([(1,packet(0),0,100.),(258,packet(1),0,100.)],shadow)
        shadow.disconnect.assert_called_once_with('ssvep_reader_queue_gap')
        self.assertEqual(shadow.gaps,1)
        self.assertEqual(shadow.packet.call_count,2)
        self.assertEqual(shadow.packet.call_args.kwargs['now'],100.)

    def test_old_future_nonfinite_time_is_not_filtered(self):
        for received in (99.49,100.01,float('nan')):
            shadow=Mock(gaps=0)
            shadow.latest={'reason':'startup'}
            self.consume([(1,packet(0),0,received)],shadow)
            shadow.packet.assert_not_called()
            shadow.disconnect.assert_called_once_with('input_backlog',publish=True)

    def test_malformed_and_adc_rails_preserved(self):
        shadow=Mock(gaps=0)
        stopped=threading.Event()
        pending=queue.Queue()
        pending.put((1,packet(0),17,100.))
        counts=np.array([0]*6+[2**23-1,-2**23])
        shadow.packet.side_effect=lambda *a,**kw:stopped.set()
        with patch('ssvep_acquisition.time.monotonic',lambda:100.):
            consume_packets(pending,stopped,shadow,lambda _:counts,.022)
        self.assertTrue(shadow.packet.call_args.args[2])
        np.testing.assert_array_equal(shadow.packet.call_args.kwargs['adc_rails'],[True,True])

    def test_same_packets_exactly_match_inline_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            now=[100.]
            with patch('ssvep_shadow.time.monotonic',lambda:now[0]):
                outputs,reference_outputs=[],[]
                lane=SSVEPShadow(ASSETS/'ssvep_causal_protocol.json',SOS,CHANNELS,
                    status_path=root/'lane.json',event_sink=outputs.append)
                ref=SSVEPShadow(ASSETS/'ssvep_causal_protocol.json',SOS,CHANNELS,
                    status_path=root/'reference.json',event_sink=reference_outputs.append)
                rows=[]
                for i in range(1000):
                    now[0]=100.+i/250
                    raw=packet(i)
                    ref.packet(decode_eeg_counts(raw).astype(np.float64)*.022,i%256,now=now[0])
                    rows.append((i+1,raw,0,now[0]))
                stopped=threading.Event()
                pending=Mock()
                def get(timeout):
                    if rows:
                        row=rows.pop(0);now[0]=row[3];return row
                    stopped.set();raise queue.Empty()
                pending.get.side_effect=get
                consume_packets(pending,stopped,lane,decode_eeg_counts,.022)
                np.testing.assert_array_equal(lane.stream.buffer,ref.stream.buffer)
                decisions=[r for r in outputs if r.get('scores') is not None]
                golden=[r for r in reference_outputs if r.get('scores') is not None]
                self.assertGreater(len(decisions),0)
                self.assertEqual([{k:v for k,v in r.items() if k!='updated_at'} for r in decisions],
                                 [{k:v for k,v in r.items() if k!='updated_at'} for r in golden])


class WorkerTests(unittest.TestCase):
    def test_page_pause_and_resume_do_not_reuse_old_ssvep_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);page=root/'page.json';status=root/'shadow.json'
            def lease(name):
                from cyton_trial_recorder import atomic_json
                atomic_json(page,dict(page=name,mode='live_readonly_hdmi',
                    physical_output_enabled=False,updated_monotonic=time.monotonic()))
            lease('video')
            owner=SSVEPReaderRuntime(ASSETS/'ssvep_causal_protocol.json',SOS,CHANNELS,
                decode_eeg_counts,.022,status_path=status,log_path=None,port=0,page_policy_path=page)
            try:
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    if json.loads(status.read_text()).get('reason')=='page_task_suspended':break
                    time.sleep(.05)
                self.assertEqual(json.loads(status.read_text())['reason'],'page_task_suspended')
                owner.reader_sink.offer(packet(0),0,time.monotonic())
                self.assertEqual(owner.reader_sink.suppressed,1)
                lease('drive');time.sleep(.3)
                owner.reader_sink.offer(packet(1),0,time.monotonic())
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    if json.loads(status.read_text()).get('reason')=='page_task_resumed':break
                    time.sleep(.05)
                result=json.loads(status.read_text())
                self.assertEqual(result['reason'],'page_task_resumed')
                self.assertFalse(result['valid'])
                self.assertIsNone(result.get('frequency_hz'))
                self.assertTrue(owner.process.is_alive())
                lease('video');time.sleep(.4)
                self.assertEqual(json.loads(status.read_text())['reason'],'page_task_suspended')
            finally:owner.close()

    def test_reader_runs_while_parent_waits_and_timeout_withdraws(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            owner=SSVEPReaderRuntime(ASSETS/'ssvep_causal_protocol.json',SOS,CHANNELS,
                decode_eeg_counts,.022,status_path=root/'synthetic-shadow.json',log_path=None,port=0,
                reader_batch_samples=10)
            bridge=SSVEPCueBridge(owner.port)
            stopped=threading.Event()
            def feed():
                began=time.monotonic()
                for batch in range(90):
                    if stopped.is_set():return
                    deadline=began+batch*.04
                    time.sleep(max(0,deadline-time.monotonic()))
                    received=time.monotonic()
                    for j in range(10):
                        i=batch*10+j
                        owner.reader_sink.offer(packet(i),0,received)
            producer=threading.Thread(target=feed,daemon=True)
            try:
                producer.start()
                # Stand in for a primary inference loop blocked for several seconds.
                producer.join(timeout=6)
                self.assertFalse(producer.is_alive())
                view=bridge.snapshot()['input']
                self.assertTrue(view['ready'],view)
                self.assertLess(view['age_seconds'],.5)
                self.assertEqual(view['frequency_hz'],12.)
                self.assertEqual(view['input_transport'],'bounded_serial_reader_tap')
                time.sleep(.65)
                result=bridge.snapshot()
                self.assertFalse(result['input']['ready'])
                self.assertFalse(result['accepted'])
                owner.close()
                self.assertFalse(owner.process.is_alive())
                self.assertEqual(bridge.snapshot()['state'],'unavailable')
                self.assertFalse(json.loads((root/'synthetic-shadow.json').read_text())['valid'])
            finally:
                stopped.set();producer.join(timeout=2);owner.close()


if __name__=='__main__':
    unittest.main()

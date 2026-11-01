import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import numpy as np

from mi_acquisition import MIAcquisition, MICandidateRuntime, task_status, CandidateHTTPServer, RemoteMISession
from mi_cued import CuedMISession
from mi_cued import hard_quality, hard_invalid
from cyton_sqi import channel_sqi
from mi_cued_server import make_handler
from test_mi_cued import Clock, Model


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.session = CuedMISession(Model(), source='replay', clock=self.clock)
        self.adapter = MIAcquisition(self.session)
        self.index = 0

    def tearDown(self):
        self.adapter.close()
        self.assertFalse(self.adapter.worker.is_alive())

    def feed(self, n=50, malformed=False):
        for i in range(n):
            self.clock.value += .004
            wave = 10*np.sin(2*np.pi*self.index/250*np.arange(8,16))
            self.adapter.packet(wave, self.index%256, malformed, received_at=self.clock())
            self.index += 1
            if (i+1)%50 == 0:
                self.adapter.pending.join()
        self.adapter.pending.join()

    def test_batch_and_exact_counter_stream(self):
        self.feed(500)
        self.assertEqual(self.session.index,500)
        self.assertEqual(self.session.previous_sequence,499%256)
        self.assertEqual(self.adapter.stats['batches'],10)

    def test_gap_withdraws_and_new_data_rewarms(self):
        self.feed(500); self.index += 1; self.feed()
        self.assertEqual(self.session.index,0)
        self.feed(500)
        self.assertEqual(self.session.snapshot()['input_state'],'ready')

    def test_malformed_clears_partial_batch(self):
        self.feed(525); self.feed(1,malformed=True)
        self.assertEqual(self.adapter.rows,[])
        self.assertEqual(self.session.index,0)

    def test_partial_stall_is_not_filled_with_old_samples(self):
        self.feed(525); self.clock.value += .6; self.adapter.idle(self.clock())
        self.assertEqual(self.adapter.rows,[])
        self.assertEqual(self.session.snapshot()['input_state'],'no_data')

    def test_oldest_timestamp_stale_is_rejected(self):
        with self.session.lock:
            self.feed(49)
            self.clock.value += .51
            self.adapter.packet(np.ones(8),49,False,received_at=self.clock())
        self.adapter.pending.join()
        self.assertEqual(self.adapter.stats['stale_batches'],1)
        self.assertEqual(self.session.index,0)

    def test_future_timestamp_refused(self):
        self.adapter.packet(np.ones(8),0,False,received_at=self.clock()+1)
        self.assertEqual(self.adapter.rows,[])

    def test_queue_full_clears_without_unbounded_growth(self):
        with self.session.lock:
            # Worker can hold at most one batch; queue remains bounded to two.
            for i in range(250):
                self.adapter.packet(np.ones(8),i%256,False,received_at=self.clock())
        self.adapter.pending.join()
        self.assertGreater(self.adapter.stats['queue_full'],0)
        self.assertLessEqual(self.adapter.pending.qsize(),2)

    def test_error_is_visible_and_does_not_escape_to_primary(self):
        self.session.feed = lambda *a,**kw: (_ for _ in ()).throw(ValueError('fixture'))
        self.feed()
        self.assertIn('fixture',self.adapter.error)
        self.assertEqual(self.session.snapshot()['input_state'],'no_data')

    def test_wrong_physical_layout_rejected_before_loading(self):
        with self.assertRaisesRegex(ValueError,'physical positions'):
            MICandidateRuntime('unused.npz',('O1',)*8,source='replay',host='127.0.0.1',
                               port=0,log_path=None,status_paths={})

    def test_concurrent_reset_never_splits_row_counter_stamp_batch(self):
        ready=threading.Barrier(2)
        def resets():
            ready.wait()
            for _ in range(100):
                self.adapter.interrupt('fixture_disconnect')
        other=threading.Thread(target=resets); other.start(); ready.wait()
        for i in range(2000):
            self.adapter.packet(np.sin(np.arange(8)+i),i%256,False,received_at=self.clock())
        other.join(timeout=20)
        self.adapter.pending.join()
        self.assertFalse(other.is_alive())
        self.assertIsNone(self.adapter.error)
        with self.adapter.state_lock:
            self.assertEqual(len(self.adapter.rows),len(self.adapter.sequences))
            self.assertEqual(len(self.adapter.rows),len(self.adapter.stamps))

    def test_reset_reuses_coefficients_with_fresh_instance_numerical_parity(self):
        self.feed(750)
        conditioner=self.session.conditioner
        conditioner_sos=conditioner.sos
        sos=self.session.band_sos
        self.session.disconnect('fixture_reset')
        self.assertIsNot(self.session.conditioner,conditioner)
        self.assertIs(self.session.conditioner.sos,conditioner_sos)
        self.assertIs(self.session.band_sos,sos)
        fresh=CuedMISession(Model(),source='replay',clock=self.clock)
        for first in range(0,750,50):
            self.clock.value += .2
            indices=np.arange(first,first+50)
            raw=10*np.sin(indices[:,None]*np.arange(8,16)[None]*2*np.pi/250)
            for session in (self.session,fresh):
                session.feed(raw,indices%256)
        np.testing.assert_array_equal(self.session.raw,fresh.raw)
        np.testing.assert_array_equal(self.session.filtered,fresh.filtered)

    def test_nonfinite_batch_is_rejected_before_filter_and_model(self):
        calls=self.session.model.calls
        for i in range(50):
            raw=np.ones(8)
            if i==13:
                raw[2]=np.nan
            self.adapter.packet(raw,i,False,received_at=self.clock())
        self.adapter.pending.join()
        self.assertIn('ValueError',self.adapter.error)
        self.assertEqual(self.session.index,0)
        self.assertIsNone(self.session.snapshot()['result'])
        self.assertEqual(self.session.model.calls,calls)

    def test_close_stops_worker_even_if_withdrawal_log_fails(self):
        original=self.session.disconnect
        def disconnect(reason):
            original(reason)
            raise OSError('fixture audit storage failed')
        self.session.disconnect=disconnect
        try:
            with self.assertRaisesRegex(OSError,'audit storage'):
                self.adapter.close()
            self.assertFalse(self.adapter.worker.is_alive())
        finally:
            self.session.disconnect=original

    def test_hard_quality_matches_full_sqi_including_boundaries(self):
        random=np.random.RandomState(42)
        for n in (50, 500, 1000):
            for gain in (0, .001, 20, 100, 1000):
                values=random.randn(n,8)*gain
                values[:,0]=0
                values[:,1]=np.arange(n)*.001
                values[::10,2]=327.66
                values[:,3]=np.where(np.arange(n)%2,100.,-100.)
                sqi=channel_sqi(values)
                np.testing.assert_array_equal(hard_quality(values),sqi[:,[1,2,3]])
                expected=bool(np.any(sqi[:,2]>=.8) or np.any(sqi[:,3]>0) or np.any(sqi[:,1]>100))
                self.assertEqual(hard_invalid(values),expected)

    def test_counts_scale_matches_per_packet_microvolt_path(self):
        fresh=CuedMISession(Model(),source='replay',clock=self.clock)
        scale=4_500_000./24/(2**23-1)
        for start in range(0,750,50):
            seq=np.arange(start,start+50)
            counts=(2000*np.sin(seq[:,None]*np.arange(8,16)[None]/250)).astype(np.int32)
            for i,row in zip(seq,counts):
                self.clock.value += .004
                self.adapter.packet(row,int(i%256),False,received_at=self.clock(),
                                    microvolts_per_count=scale)
            self.adapter.pending.join()
            fresh.feed(counts.astype(np.float64)*scale,seq%256,received_monotonic=self.clock())
        np.testing.assert_array_equal(self.session.raw,fresh.raw)
        np.testing.assert_array_equal(self.session.filtered,fresh.filtered)

    def test_gain_change_clears_partial_batch_and_old_candidate(self):
        self.feed(525)
        self.session.command(dict(action='start',target='left'))
        self.adapter.packet(np.ones(8,dtype=np.int32),13,False,received_at=self.clock(),
                            microvolts_per_count=.022)
        self.assertEqual(len(self.adapter.rows),1)
        self.assertEqual(self.session.index,0)
        self.assertEqual(self.session.snapshot()['reason'],'acquisition_gain_changed')

    def test_invalid_gain_rejected(self):
        for gain in (0.,-1.,float('nan'),float('inf')):
            self.adapter.packet(np.ones(8),0,False,received_at=self.clock(),microvolts_per_count=gain)
            self.assertEqual(self.adapter.rows,[])


class EntryTests(unittest.TestCase):
    def test_trusted_worker_pipe_transmits_exact_data_and_withdrawal(self):
        import multiprocessing
        import time
        parent,child=multiprocessing.Pipe()
        session=CuedMISession(Model(),source='replay')
        remote=RemoteMISession(parent,session.snapshot())
        def worker():
            while True:
                request=child.recv()
                action=request['action']
                if action=='feed':
                    session.feed(request['values'],request['sequences'],received_monotonic=request['received'])
                elif action in ('disconnect','close'):
                    session.disconnect(request.get('reason','fixture_close'))
                child.send(dict(snapshot=session.snapshot(),last_received=session.last_received,error=None))
                if action=='close':break
        thread=threading.Thread(target=worker);thread.start()
        try:
            remote.feed(np.sin(np.arange(400).reshape(50,8)),np.arange(50),received_monotonic=time.monotonic())
            self.assertEqual(remote.snapshot()['received_samples'],50)
            self.assertEqual(remote.disconnect('fixture_gap')['input_state'],'no_data')
            remote.request('close')
        finally:
            thread.join(timeout=2);parent.close();child.close()
        self.assertFalse(thread.is_alive())

    def test_worker_disconnect_never_returns_old_candidate(self):
        import multiprocessing
        parent,child=multiprocessing.Pipe();child.close()
        initial=dict(CuedMISession(source='replay').snapshot(),result=dict(label='left'))
        remote=RemoteMISession(parent,initial)
        value=remote.snapshot()
        self.assertIsNone(value['result'])
        self.assertEqual(value['input_state'],'no_data')
        self.assertIn('worker',value['reason'])
        self.assertIsNotNone(remote.error)
        self.assertTrue(remote.closed)

    def test_worker_timeout_closes_pipe_and_clears_results(self):
        connection=unittest.mock.Mock()
        connection.poll.return_value=False
        remote=RemoteMISession(connection,dict(CuedMISession().snapshot(),result=dict(label='right')))
        value=remote.snapshot()
        connection.poll.assert_called_once_with(.5)
        connection.close.assert_called_once()
        self.assertIsNone(value['result'])
        self.assertEqual(value['input_state'],'no_data')

    def test_slow_incomplete_http_connection_times_out_then_recovers(self):
        import socket
        session=CuedMISession(source='replay')
        server=CandidateHTTPServer(('127.0.0.1',0),make_handler(session))
        worker=threading.Thread(target=server.serve_forever); worker.start()
        url='http://127.0.0.1:'+str(server.server_port)
        try:
            with socket.create_connection(server.server_address,timeout=2) as connection:
                connection.sendall(b'GET /api/mi-cue HTTP/1.1\r\nHost: fixture\r\n')
                with urlopen(url+'/api/mi-cue',timeout=2) as response:
                    self.assertEqual(json.load(response)['input_state'],'no_data')
        finally:
            server.shutdown(); worker.join(); server.server_close()

    def test_entry_api_and_no_result_injection(self):
        session = CuedMISession(source='replay')
        server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(session,
                     multitask=lambda:dict(source='replay',control_enabled=False,tasks={})))
        worker=threading.Thread(target=server.serve_forever); worker.start()
        url='http://127.0.0.1:'+str(server.server_port)
        try:
            with urlopen(url+'/') as response:
                self.assertIn(b'/mi-cued',response.read())
            with urlopen(url+'/api/multitask') as response:
                value=json.load(response)
            self.assertEqual(value['mi']['source'],'replay')
            self.assertFalse(value['mi']['control_enabled'])
            req=Request(url+'/api/mi-cue',data=b'{"action":"upload","result":"right"}',
                        headers={'Content-Type':'application/json','Origin':url})
            with self.assertRaises(HTTPError) as e:
                urlopen(req)
            self.assertEqual(e.exception.code,400)
            req=Request(url+'/api/mi-cue',data=b'{"action":"start","target":"left"}',
                        headers={'Content-Type':'application/json','Origin':'http://wrong-host'})
            with self.assertRaises(HTTPError) as e:
                urlopen(req)
            self.assertEqual(e.exception.code,403)
        finally:
            server.shutdown(); worker.join(); server.server_close()

    def test_old_task_status_is_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'status.json'
            path.write_text('{"updated_at":1,"valid":true}')
            value=task_status({'primary':path},'replay')
            self.assertTrue(value['tasks']['primary']['stale'])
            self.assertEqual(value['tasks']['primary']['payload'],{})
            self.assertFalse(value['real'])

    def test_task_summary_retains_state_not_waveforms_and_marks_source(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'status.json'
            path.write_text(json.dumps(dict(updated_at=time.time(), valid=True, state='prediction',
                           source='bci', sqi={'channels':[1]*800}, emotion=dict(valid=True,label='bored',
                           scores=[1]*800), score=.4)),encoding='utf-8')
            value=task_status({'primary':path},'replay')['tasks']['primary']
            self.assertFalse(value['stale'])
            self.assertEqual(value['payload']['emotion'],dict(valid=True,label='bored'))
            self.assertEqual(value['payload']['source'],'replay')
            self.assertNotIn('sqi',value['payload'])
            self.assertFalse(value['payload']['control_enabled'])


if __name__=='__main__':
    unittest.main()

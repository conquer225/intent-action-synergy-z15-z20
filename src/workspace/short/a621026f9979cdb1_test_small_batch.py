"""No hardware access; numeric and telemetry API regression checks."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from cyton_sqi import CausalEEGFilter
from cyton_trial_recorder import atomic_json
from guardianloop_web import TelemetryResponseCache


class SmallBatchTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='posix','Acquisition module requires termios')
    def test_old_input_never_becomes_valid_published_prediction(self):
        from cyton_guardianloop import publish_result
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'status.json'
            value={'valid':True,'state':'NORMAL','perclos':.2,'smoothed_perclos':.2,
                   'emotion':{'valid':True,'label':'calm'}}
            publish_result(value,True,path,'',input_age_seconds=13.)
            payload=json.loads(path.read_text())
            self.assertFalse(payload['valid']);self.assertIsNone(payload['score'])
            self.assertFalse(payload['emotion']['valid'])
            self.assertEqual(payload['reason'],'PROCESSING_BACKLOG')
            self.assertTrue(value['valid'])
            publish_result(value,True,path,'',input_age_seconds=.2)
            self.assertTrue(json.loads(path.read_text())['valid'])

    @unittest.skipUnless(os.name=='posix','Writer uses Linux fork')
    def test_display_queue_is_bounded_and_worker_failure_is_visible(self):
        import cyton_guardianloop as live
        original=live.publish_telemetry
        def slow_write(*args, **kwargs):
            time.sleep(.15)
            original(*args, **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'telemetry.json'
            x=np.ones((20,8))
            with patch.object(live,'publish_telemetry',slow_write):
                writer=live.TelemetryWriter()
                try:
                    for _ in range(100):writer.submit(x,x,20,path,40,0,0,0,0,0,None,None)
                    self.assertGreater(writer.skipped,0)
                finally:writer.close()
            self.assertFalse(writer.worker.is_alive())
            writer=live.TelemetryWriter()
            writer.worker.terminate();writer.worker.join(timeout=2)
            try:
                with self.assertRaisesRegex(RuntimeError,'Telemetry writer stopped'):
                    writer.submit(x,x,20,path,40,0,0,0,0,0,None,None)
            finally:writer.close()

    @unittest.skipUnless(os.name=='posix','Writer uses Linux fork')
    def test_writer_isolated_snapshot_and_shutdown(self):
        from cyton_guardianloop import TelemetryWriter
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'replay-telemetry.json'
            writer=TelemetryWriter()
            x=np.arange(160,dtype=float).reshape(20,8)/7
            with patch('cyton_guardianloop.time.time', return_value=123.):
                writer.submit(x,x+1,20,path,40,0,0,0,0,0,None,None)
            writer.close()
            self.assertFalse(writer.worker.is_alive())
            result=json.loads(path.read_text())
            self.assertEqual(result['updated_at'],123.)
            self.assertEqual(result['runtime']['display_snapshots_skipped'],0)
            np.testing.assert_array_equal(result['samples'],np.round(x,3))
            self.assertEqual(result['sample_index'],20)

    def test_chunk_boundaries_preserve_filter_state(self):
        x = np.random.RandomState(18).normal(size=(2030, 8)) * 20
        sample_filter = CausalEEGFilter()
        expected = np.concatenate([sample_filter.process(row[None]) for row in x])
        for size in (5, 10, 25):
            block_filter = CausalEEGFilter()
            actual = np.concatenate([block_filter.process(x[i:i+size]) for i in range(0, len(x), size)])
            np.testing.assert_allclose(actual, expected, atol=1e-10, rtol=1e-10)
            np.testing.assert_allclose(block_filter.zi, sample_filter.zi, atol=1e-10, rtol=1e-10)

    def test_cache_preserves_waveforms_and_expires_without_file_change(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'telemetry.json'
            payload = {'updated_at':100., 'source':'cyton_usb', 'real':True,
                       'samples':[[1.125]*8], 'raw_samples':[[1000.5]*8], 'sample_index':7}
            atomic_json(path, payload)
            cache = TelemetryResponseCache(path)
            with patch('guardianloop_web.time.time', return_value=101.):
                self.assertEqual(json.loads(cache.body()), {'telemetry':payload,'stale':False,'snapshot_age_seconds':1.,'data_age_seconds':1.})
                with patch.object(Path, 'read_bytes', side_effect=AssertionError('cache reread')):
                    self.assertFalse(json.loads(cache.body())['stale'])
            with patch('guardianloop_web.time.time', return_value=104.):
                self.assertTrue(json.loads(cache.body())['stale'])
            payload.update(updated_at=104., sample_index=8, offline=True, real=False, source='replay')
            atomic_json(path, payload)
            with patch('guardianloop_web.time.time', return_value=105.):
                self.assertEqual(json.loads(cache.body()), {'telemetry':payload,'stale':False,'snapshot_age_seconds':1.,'data_age_seconds':1.})
            path.write_text('{broken')
            self.assertEqual(json.loads(cache.body()), {'telemetry':{},'stale':True})
            path.unlink()
            self.assertTrue(json.loads(cache.body())['stale'])

    def test_cached_diagnostics_age_and_loss_are_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'telemetry.json'
            payload={'updated_at':100.,'real':True,'source':'cyton_usb',
                     'packet_loss_percent':0.,'dropped_packets':0,
                     'runtime':{'display_snapshots_skipped':17,'reader_queue_delay_ms':4.5}}
            atomic_json(path,payload)
            cache=TelemetryResponseCache(path)
            with patch('guardianloop_web.time.time',return_value=102.):
                response=json.loads(cache.body())
                self.assertEqual(response['snapshot_age_seconds'],2.)
                self.assertEqual(response['telemetry']['packet_loss_percent'],0.)
                self.assertEqual(response['telemetry']['runtime']['display_snapshots_skipped'],17)
            with patch('guardianloop_web.time.time',return_value=104.):
                self.assertTrue(json.loads(cache.body())['stale'])

    def test_new_snapshot_with_old_input_is_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'telemetry.json'
            atomic_json(path,{'updated_at':100.,'runtime':{'input_age_at_snapshot_ms':13000}})
            cache=TelemetryResponseCache(path)
            with patch('guardianloop_web.time.time',return_value=100.2):
                result=json.loads(cache.body())
                self.assertTrue(result['stale'])
                self.assertAlmostEqual(result['snapshot_age_seconds'],.2)
                self.assertAlmostEqual(result['data_age_seconds'],13.2)
                self.assertTrue(cache.freshness()['stale'])

    def test_clock_rollback_cannot_make_old_waveform_fresh(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'telemetry.json'
            atomic_json(path,{'updated_at':100.,'samples':[[7.]*8]})
            cache=TelemetryResponseCache(path)
            with patch('guardianloop_web.time.time',return_value=101.):
                self.assertFalse(cache.freshness()['stale'])
            with patch('guardianloop_web.time.time',return_value=99.):
                value=json.loads(cache.body())
                self.assertTrue(value['stale'])
                self.assertIsNone(value['data_age_seconds'])
                self.assertEqual(value['telemetry']['samples'],[[7.]*8])


if __name__ == '__main__':
    unittest.main()

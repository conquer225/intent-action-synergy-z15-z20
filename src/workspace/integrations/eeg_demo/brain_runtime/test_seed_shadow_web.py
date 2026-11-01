import json
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest.mock import patch
from pathlib import Path
from http.server import ThreadingHTTPServer
import guardianloop_web as web


class ShadowWebTests(unittest.TestCase):
    def test_waiting_state_survives_stale_snapshot_without_exposing_old_prediction(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'status').write_text(json.dumps({'updated_at':time.time()-100,
                'valid':False,'state':'invalid','reason':'WAITING_FOR_CYTON',
                'calibration_current':15,'calibration_retained':True,
                'emotion':{'valid':True,'label':'calm'}}))
            (root/'telemetry').write_text(json.dumps({'updated_at':time.time()-68431}))
            with patch.object(web,'system_status',return_value={}):
                server=ThreadingHTTPServer(('127.0.0.1',0),web.make_handler(root/'status',root/'telemetry',20))
                worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
                try:
                    with urllib.request.urlopen('http://127.0.0.1:%s/api/status'%server.server_port) as response:
                        result=json.load(response)
                    self.assertTrue(result['stale'])
                    self.assertFalse(result['fatigue']['valid'])
                    self.assertFalse(result['fatigue']['emotion']['valid'])
                    self.assertEqual(result['fatigue']['reason'],'WAITING_FOR_CYTON')
                    self.assertEqual(result['fatigue']['calibration_current'],15)
                    self.assertTrue(result['fatigue']['calibration_retained'])
                finally:
                    server.shutdown();server.server_close();worker.join()

    def test_seed_candidate_is_separate_and_labeled_as_exploratory(self):
        page = web.PAGE
        self.assertIn('SEED 正／中／负影片条件 · 八通道候选', page)
        self.assertIn('F3、F4、C3、C4、T7、T8、O1、O2', page)
        self.assertIn('硬故障拒绝；软统计偏离会标记警告', page)
        self.assertIn('逐人留出', page)
        self.assertIn('不是当前佩戴者的准确率', page)
        self.assertIn('历史离线回放（非当前佩戴者）', page)
        self.assertIn("v.source==='live'&&v.valid&&v.state==='prediction'", page)
        self.assertLess(page.index('id="emotion"'), page.index('id="seedShadow"'))
        self.assertLess(page.index('id="seedShadow"'), page.index('id="rawInterference"'))

    def test_backlog_masks_primary_and_shadow_until_fresh_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            stamp=time.time()
            (root/'status').write_text(json.dumps({'updated_at':stamp,'valid':True,'score':.7,
                'emotion':{'valid':True,'label':'calm'}}))
            (root/'seed').write_text(json.dumps({'updated_at':stamp,'valid':True,'class_id':1,'source':'live'}))
            (root/'telemetry').write_text(json.dumps({'updated_at':stamp,
                'runtime':{'input_age_at_snapshot_ms':13000}}))
            with patch.object(web,'LIVE_PATH',root/'seed'),patch.object(web,'REPLAY_PATH',root/'replay'),patch.object(web,'system_status',return_value={}):
                server=ThreadingHTTPServer(('127.0.0.1',0),web.make_handler(root/'status',root/'telemetry',20))
                worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
                url='http://127.0.0.1:%s'%server.server_port
                try:
                    primary=json.load(urllib.request.urlopen(url+'/api/status'))
                    self.assertTrue(primary['stale']);self.assertFalse(primary['fatigue']['valid'])
                    self.assertIsNone(primary['fatigue']['score'])
                    self.assertFalse(primary['fatigue']['emotion']['valid'])
                    shadow=json.load(urllib.request.urlopen(url+'/api/seed-shadow'))
                    self.assertFalse(shadow['live']['valid']);self.assertNotIn('class_id',shadow['live'])
                    web.atomic_json(root/'telemetry',{'updated_at':time.time(),'runtime':{'input_age_at_snapshot_ms':20}})
                    primary=json.load(urllib.request.urlopen(url+'/api/status'))
                    self.assertFalse(primary['stale']);self.assertTrue(primary['fatigue']['valid'])
                    shadow=json.load(urllib.request.urlopen(url+'/api/seed-shadow'))
                    self.assertTrue(shadow['live']['valid'])
                finally:
                    server.shutdown();server.server_close();worker.join()

    def test_stale_live_status_cannot_expose_valid_primary_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'status').write_text(json.dumps({
                'updated_at': time.time()-30, 'valid': True, 'score': .9,
                'raw_ratio': .8, 'level': 'severe',
                'emotion': {'valid': True, 'label': 'calm'}}))
            (root/'telemetry').write_text(json.dumps({
                'updated_at': time.time(), 'runtime': {'input_age_at_snapshot_ms': 10}}))
            with patch.object(web, 'system_status', return_value={}):
                server = ThreadingHTTPServer(('127.0.0.1', 0),
                    web.make_handler(root/'status', root/'telemetry', 20))
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    url = 'http://127.0.0.1:%s/api/status' % server.server_port
                    result = json.load(urllib.request.urlopen(url))
                    self.assertTrue(result['stale'])
                    self.assertFalse(result['fatigue']['valid'])
                    self.assertIsNone(result['fatigue']['score'])
                    self.assertEqual(result['fatigue']['level'], 'unknown')
                    self.assertEqual(result['fatigue']['reason'], 'STALE_STATUS')
                    self.assertFalse(result['fatigue']['emotion']['valid'])
                finally:
                    server.shutdown();server.server_close();worker.join()

    def test_input_or_status_lost_during_service_lookup_is_withdrawn(self):
        for changed_file, reason in (('telemetry', 'STALE_EEG'), ('status', 'STALE_STATUS')):
            with self.subTest(changed_file=changed_file), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                status = {'updated_at': time.time(), 'valid': True, 'score': .7,
                          'emotion': {'valid': True, 'label': 'calm'}}
                telemetry = {'updated_at': time.time(),
                             'runtime': {'input_age_at_snapshot_ms': 10}}
                web.atomic_json(root/'status', status)
                web.atomic_json(root/'telemetry', telemetry)

                def lookup():
                    # Simulate input/status expiring while systemctl is blocked.
                    expired = (dict(telemetry, runtime={'input_age_at_snapshot_ms': 13000})
                               if changed_file == 'telemetry' else
                               dict(status, updated_at=time.time()-30))
                    web.atomic_json(root/changed_file, expired)
                    return {'acquisition_active': True}

                with patch.object(web, 'system_status', side_effect=lookup):
                    server = ThreadingHTTPServer(('127.0.0.1', 0),
                        web.make_handler(root/'status', root/'telemetry', 20))
                    worker = threading.Thread(target=server.serve_forever, daemon=True)
                    worker.start()
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:%s/api/status' %
                                                    server.server_port) as response:
                            result = json.load(response)
                        self.assertTrue(result['stale'])
                        self.assertFalse(result['fatigue']['valid'])
                        self.assertIsNone(result['fatigue']['score'])
                        self.assertEqual(result['fatigue']['reason'], reason)
                        self.assertFalse(result['fatigue']['emotion']['valid'])
                    finally:
                        server.shutdown();server.server_close();worker.join()

    def test_stale_live_never_exposes_class_and_replay_stays_separate(self):
        previous=(web.LIVE_PATH,web.REPLAY_PATH)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            web.LIVE_PATH,web.REPLAY_PATH=root/'live.json',root/'replay.json'
            web.LIVE_PATH.write_text(json.dumps({'updated_at':time.time()-10,'valid':True,'class_id':1,'source':'live'}))
            web.REPLAY_PATH.write_text(json.dumps({'updated_at':time.time(),'source':'replay','finished':True,'valid':False}))
            server=ThreadingHTTPServer(('127.0.0.1',0),web.make_handler(root/'status',root/'telemetry',6))
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                url='http://127.0.0.1:%s/api/seed-shadow'%server.server_port
                result=json.load(urllib.request.urlopen(url))
                self.assertTrue(result['stale'])
                self.assertFalse(result['live']['valid'])
                self.assertNotIn('class_id',result['live'])
                self.assertEqual(result['replay']['source'],'replay')
                self.assertTrue(result['replay']['finished'])
            finally:
                server.shutdown();server.server_close();worker.join()
                web.LIVE_PATH,web.REPLAY_PATH=previous


if __name__=='__main__':
    unittest.main()

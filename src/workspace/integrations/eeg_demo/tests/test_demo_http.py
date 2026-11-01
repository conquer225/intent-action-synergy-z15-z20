import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'runtime'),str(ROOT/'runtime/system_runtime'),str(ROOT/'runtime/system_runtime/wheelchair_ssvep')]
import media_server as media
from eeg_demo_bridge import DemoBridge


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=media.MediaStore(self.tmp.name,'secret','unused')
        self.server=media.make_server('127.0.0.1',0,self.store)
        self.server.RequestHandlerClass=media.MediaHandler
        self.server.demo_lock=threading.Lock();self.server.eeg_demo=DemoBridge(fetch=lambda _: {'stale':True},autostart=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.finish)
    def finish(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.server.eeg_demo.close();self.tmp.cleanup()
    def request(self,path,key='secret',origin=None,method='GET'):
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=2)
        headers={'X-Media-Key':key}
        if origin:headers['Origin']=origin
        client.request(method,path,headers=headers);reply=client.getresponse();body=reply.read();result=(reply.status,body,dict(reply.getheaders()));client.close();return result
    def test_readonly_snapshot_requires_original_auth_and_exposes_no_command_endpoint(self):
        self.assertEqual(self.request('/api/eeg-demo',key='bad')[0],403)
        self.assertEqual(self.request('/api/eeg-demo',origin='http://foreign.invalid')[0],403)
        code,body,headers=self.request('/api/eeg-demo');self.assertEqual(code,200)
        self.assertTrue(json.loads(body)['stale']);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.request('/api/eeg-demo?url=http://foreign.invalid')[0],404)
        self.assertEqual(self.request('/api/eeg-demo',method='POST')[0],404)
    def test_static_assets_and_control_console_are_both_available(self):
        for path in ('/eeg-demo','/eeg_demo.css','/eeg_demo.js','/eeg_demo_core.js','/presentation.css','/eeg_recording.json','/'):
            code,body,_=self.request(path);self.assertEqual(code,200,path);self.assertGreater(len(body),100)


if __name__=='__main__':unittest.main()

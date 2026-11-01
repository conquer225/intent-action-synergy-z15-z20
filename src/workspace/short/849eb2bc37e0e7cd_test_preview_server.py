import http.client
import json
import threading
import unittest

from guardianloop_system.preview_server import make_server


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.server=make_server(key='test-key');self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start();self.addCleanup(self.finish)

    def finish(self):self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,body=None,key='test-key',origin=None,host=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={'X-Preview-Key':key}
        if origin:headers['Origin']=origin
        if host:headers['Host']=host
        try:
            conn.request('POST' if body else 'GET','/api/action' if body else '/api/state',
                None if body is None else json.dumps(body),headers)
            response=conn.getresponse();return response.status,json.loads(response.read())
        finally:conn.close()

    def test_authentication_origin_and_host_guards(self):
        self.assertEqual(self.request(key='wrong')[0],403)
        self.assertEqual(self.request({'action':'mood'},origin='http://foreign')[0],403)
        self.assertEqual(self.request({'action':'mood'},host='foreign:9120')[0],403)

    def test_status_explicitly_simulated_and_silent(self):
        code,data=self.request();self.assertEqual(code,200)
        self.assertEqual(data['mode'],'manual_simulation_only')
        for name in ('audio_output','physical_output_enabled','live_eeg_connected','live_gaze_connected','stimulus_enabled'):
            self.assertFalse(data[name])

    def test_no_arbitrary_paths_device_writes_or_uploaded_eeg(self):
        for data in ({'action':'motor','value':'forward'},{'action':'mood','path':'/boot'},
                     {'action':'ssvep','value':99},{'action':'mi','value':'fake-result'}):
            self.assertEqual(self.request(data)[0],400)

    def test_candidate_label_and_self_report_are_different(self):
        candidate=self.request({'action':'gameemo'})[1]
        self.assertEqual(candidate['page'],'home')
        self.assertEqual(candidate['monitor_labels']['emotion']['source'],'GAMEEMO_condition')
        self.assertNotIn('mood',candidate['alerts'])
        self.assertEqual(self.request({'action':'mood'})[1]['page'],'music_offer')


if __name__=='__main__':unittest.main()

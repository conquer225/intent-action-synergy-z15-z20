import sys
import time
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from eeg_demo_bridge import DemoBridge

CAP=['F3','F4','C3','C4','T7','T8','O1','O2']


class BridgeTests(unittest.TestCase):
    def test_fixed_readonly_endpoints_and_expiry_revoke_old_output(self):
        calls=[];clock=[100.]
        def fetch(path):
            calls.append(path)
            if path=='/api/status':return {'stale':False,'fatigue':{'source':'bci','valid':True,'level':'normal','channel_map':CAP}}
            return {'stale':False,'data_age_seconds':.1,'telemetry':{'real':True,'sample_rate_hz':125,
                'channels':CAP,'samples':[[1.]*8],'raw_samples':[[2.]*8],'sample_index':1}}
        bridge=DemoBridge(fetch=fetch,clock=lambda:clock[0],autostart=False)
        bridge.refresh();view=bridge.snapshot()
        self.assertEqual(calls,['/api/status','/api/telemetry'])
        self.assertFalse(view['stale']);self.assertEqual(view['status']['fatigue']['level'],'normal')
        clock[0]+=4
        self.assertTrue(bridge.snapshot()['stale'])
        self.assertEqual(bridge.snapshot()['status'],{})
        self.assertEqual(bridge.snapshot()['telemetry'],{})
        bridge.close()

    def test_bad_or_offline_upstream_never_looks_live(self):
        for payload in ({'stale':True}, {'stale':False,'fatigue':{'offline':True}},[]):
            with self.subTest(payload=payload):
                bridge=DemoBridge(fetch=lambda path:payload,autostart=False)
                bridge.refresh();self.assertTrue(bridge.snapshot()['stale']);bridge.close()


if __name__=='__main__':unittest.main()

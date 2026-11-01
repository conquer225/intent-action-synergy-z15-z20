import json,unittest
from intent_one.monitor import PendulumReader,ProcessModel,BrainApi
class MonitorTests(unittest.TestCase):
    def test_stm_datagram_validation_and_boot_reset(self):
        r=PendulumReader('192.168.4.1')
        row=dict(v=1,type='stm_raw',session=3,seq=1,received_ms=1,time_ms=200,adc=2050,location=-12,pwm=35)
        self.assertIsNone(r.feed(json.dumps(row).encode(),'192.168.4.2',0))
        self.assertEqual(r.feed(json.dumps(row).encode(),'192.168.4.1',0)['adc'],2050)
        self.assertIsNone(r.feed(json.dumps(row).encode(),'192.168.4.1',0))
        self.assertIsNone(r.snapshot(1))
    def test_gap_revokes_rms_and_contact_is_readonly(self):
        model=ProcessModel()
        row=dict(type='raw',samples=[1,3]*5,discontinuity=False,valid=True)
        for _ in range(5):model.observe(row)
        self.assertEqual(model.rms,1)
        model.observe(dict(row,discontinuity=True));self.assertIsNone(model.rms)
        model.observe(dict(type='contact',pressed=True,valid=True,session=1,event_id=2))
        self.assertTrue(model.pressed)
    def test_api_never_promotes_replay_or_expired_live_candidate(self):
        api=BrainApi(start=False)
        api.rows['ssvep-shadow']=({'live':{'source':'replay','valid':True},'stale':False},0,None)
        self.assertIsNone(api.candidate(.1))
        api.rows['ssvep-shadow']=({'live':{'source':'live','valid':True},'stale':False},0,None)
        self.assertIsNotNone(api.candidate(.1));self.assertIsNone(api.candidate(2))
if __name__=='__main__':unittest.main()

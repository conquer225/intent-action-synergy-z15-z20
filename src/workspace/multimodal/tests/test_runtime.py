import json
import unittest
from intent_one.telemetry import SignalReader
from intent_one.tasks import TaskController
from intent_one.reference import WindowStatistics

class Transport:
    def __init__(self,source): self.source=source; self.commands=[]; self.connected=False
    def connect(self): self.connected=True
    def send(self,device,action,**fields):
        self.commands.append((device,action,fields)); return {'ok':True,'status':{'hand':{'enabled':False},'pendulum':{'enabled':False}}}
    def close(self): self.connected=False

class RuntimeTests(unittest.TestCase):
    def test_remote_disable_never_reenables_on_recovery(self):
        c=TaskController(Transport);c.select('eye','hand');c.enable()
        c.sync({'hand':{'enabled':False},'pendulum':{'enabled':False}})
        self.assertFalse(c.enabled)
        c.sync({'hand':{'enabled':True},'pendulum':{'enabled':False}})
        self.assertFalse(c.enabled)
    def test_raw_stream_fragments_and_duplicate_do_not_repeat_samples(self):
        reader=SignalReader()
        row=dict(v=1,type='raw',session=1,seq=1,time_us=2000,sample_index=0,sample_rate_hz=500,
                 samples=list(range(10)),dt_us=[2000]*10,wear_mask=1023,valid=True,dropped=0)
        data=(json.dumps(row)+'\n').encode()
        self.assertEqual(reader.feed(data[:30],1),[])
        self.assertEqual(len(reader.feed(data[30:],1)),1)
        self.assertEqual(reader.feed(data,1.1),[])
        self.assertEqual(reader.snapshot(2)['state'],'stale')
    def test_gap_and_new_boot_invalidate_accumulated_window(self):
        r=SignalReader()
        a=dict(v=1,type='raw',session=1,seq=1,time_us=2,sample_index=0,sample_rate_hz=500,
               samples=[2000]*10,dt_us=[2000]*10,wear_mask=1023,valid=True,dropped=0)
        r.feed((json.dumps(a)+'\n').encode(),0)
        a.update(seq=2,sample_index=20)
        self.assertTrue(r.feed((json.dumps(a)+'\n').encode(),.1)[0]['discontinuity'])
        a.update(session=2,seq=1,sample_index=0)
        self.assertTrue(r.feed((json.dumps(a)+'\n').encode(),.2)[0]['discontinuity'])
    def test_source_switch_stops_and_requires_explicit_enable(self):
        peers=[]
        def factory(source):
            p=Transport(source); peers.append(p); return p
        c=TaskController(factory)
        c.select('eye','hand'); self.assertFalse(c.enabled)
        with self.assertRaises(RuntimeError): c.action('close')
        c.enable(); c.action('close')
        c.select('brain','pendulum')
        self.assertEqual(peers[0].commands[-1][:2],('all','estop'))
        self.assertFalse(c.enabled)
        with self.assertRaises(RuntimeError): c.action('start')
    def test_event_reuse_or_wrong_mode_cannot_execute(self):
        c=TaskController(Transport); c.select('eye','hand'); c.enable()
        event=dict(id=1,session='a',mode='eye',action='close',valid=True,received_at=1,age_s=0)
        self.assertTrue(c.event(event,1))
        self.assertFalse(c.event(event,1.1))
        event.update(id=2,mode='brain'); self.assertFalse(c.event(event,1.1))
        event.update(mode='eye'); self.assertFalse(c.event(event,3))
    def test_ac_rms_has_independent_known_answer_and_resets_after_gap(self):
        stats=WindowStatistics(4)
        self.assertEqual(stats.process([1,3,1,3])[0],{'count':4,'mean':2.0,'variance':1.0,'rms':1.0})
        self.assertEqual(stats.process([100,100]),[])
        stats.reset()
        self.assertEqual(stats.process([0,0,0,0])[0]['rms'],0)

if __name__=='__main__': unittest.main()

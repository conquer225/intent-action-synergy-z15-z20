import unittest
from intent_one.board import DisplayWitness,SignalDma
class Mmio:
    def __init__(self):self.values={0x00:0x53494731};self.writes=[]
    def read(self,a):return self.values.get(a,0)
    def write(self,a,v):self.writes.append((a,v))
class BoardTests(unittest.TestCase):
    def test_pixel_counter_wrap_keeps_elapsed_time(self):
        w=DisplayWitness()
        row={'epoch':7,'frames':0,'ticks':0,'rising':[0]*4,'max_gap':1250000,'active':True}
        w.observe(row,0)
        w.observe(dict(row,frames=1800,ticks=2250000000,rising=[240,300,360,420]),30)
        result=w.observe(dict(row,frames=3600,ticks=4500000000&0xffffffff,rising=[480,600,720,840]),60)
        self.assertEqual(result['seconds'],60);self.assertEqual(result['rates'],[8,10,12,14])
    def test_display_rates_come_from_counter_deltas(self):
        witness=DisplayWitness();a={'epoch':7,'frames':10,'ticks':100,'rising':[1,1,2,2],'max_gap':1250000,'active':True}
        self.assertEqual(witness.observe(a,0)['seconds'],0)
        b=dict(a,frames=130,ticks=150000100,rising=[17,21,26,30])
        row=witness.observe(b,2)
        self.assertEqual(row['rates'],[8,10,12,14]);self.assertEqual(row['refresh_hz'],60)
        self.assertAlmostEqual(row['max_gap_ms'],16.6666667)
        self.assertEqual(witness.observe(dict(b,epoch=8),3)['seconds'],0)
    def test_dma_stops_and_resets_before_buffer_release_on_timeout(self):
        dma=Mmio();core=Mmio();log=[]
        class Buffer(list):
            physical_address=1024
            def flush(self):pass
            def invalidate(self):pass
            def freebuffer(self):log.append('free')
        def allocate(**kwargs):return Buffer([0]*kwargs['shape'][0])
        clock=iter([0,0,.1,.2,.3,.4,.5,.6,1,2,3,4,5])
        runner=SignalDma(dma,core,allocate,clock=lambda:next(clock),pause=lambda _:None)
        with self.assertRaises(TimeoutError):runner.process([1000],timeout=.2)
        self.assertTrue(any(v&4 for a,v in dma.writes if a in (0,0x30)))
        self.assertEqual(log,[]) # Cannot confirm reset completion: retain leased memory.
if __name__=='__main__':unittest.main()

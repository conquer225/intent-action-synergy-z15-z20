import unittest
from intent_one.pipeline import LiveSignalPipeline
class Runner:
    def __init__(self):self.windows=0;self.input=[]
    def configure(self,**_):self.windows=0;self.input=[]
    def process(self,values,**_):self.input=list(values);self.windows+=1;return values
    def stats(self):return dict(windows=self.windows,sum=sum(self.input),squares=sum(v*v for v in self.input),saturations=0)
class PipelineTests(unittest.TestCase):
    def test_live_raw_reaches_pl_and_resets_partial_window_on_gap(self):
        r=Runner();p=LiveSignalPipeline(r)
        row=dict(type='raw',samples=[1,3]*5,valid=True,discontinuity=False)
        for _ in range(4):self.assertIsNone(p.observe(row))
        self.assertEqual(p.observe(row)['pl_rms'],1)
        p.observe(row);self.assertIsNone(p.observe(dict(row,discontinuity=True)))
        self.assertEqual(p.last,None)
if __name__=='__main__':unittest.main()

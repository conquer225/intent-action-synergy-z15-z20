"""Live S3 blocks enter the persistent PL. Gaps revoke partial statistics."""
import math,time
class LiveSignalPipeline:
    def __init__(self,runner):self.runner=runner;self.reset()
    def reset(self):
        self.pending=[];self.last=None
        self.runner.configure(coefficient=16384,channels=1,window=50,bypass=True)
    def observe(self,row):
        if row.get('type')!='raw':return None
        if row.get('discontinuity') or row.get('valid') is not True:self.reset()
        if row.get('valid') is not True:return None
        self.pending.extend(row['samples'])
        if len(self.pending)<50:return None
        values=self.pending[:50];del self.pending[:50];began=time.perf_counter()
        output=self.runner.process(values,timeout=.05);stats=self.runner.stats()
        if output!=values or stats['sum']!=sum(values) or stats['squares']!=sum(v*v for v in values) or stats['saturations']:
            raise RuntimeError('live PS/PL raw parity failed')
        rms=math.sqrt(max(0,stats['squares']/50.-(stats['sum']/50.)**2))
        self.last=dict(pl_rms=rms,pl_ms=(time.perf_counter()-began)*1000,windows=stats['windows'],origin='s3_live')
        return self.last

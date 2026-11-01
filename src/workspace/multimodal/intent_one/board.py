"""Bounded DMA and measured PL display counters. Import has no board effects."""
import time
_QUARANTINED=[]

class DisplayWitness:
    def __init__(self):self.first=None;self.previous=None;self.elapsed=0
    def observe(self,row,now):
        if self.first is None or self.first['epoch']!=row['epoch'] or row['frames']<self.first['frames']:
            self.first=dict(row)
            self.previous=dict(row);self.elapsed=0
        self.elapsed+=((row['ticks']-self.previous['ticks'])&0xffffffff)/75000000.
        self.previous=dict(row);seconds=self.elapsed
        return dict(epoch=row['epoch'],active=row['active'],seconds=seconds,
                    refresh_hz=(row['frames']-self.first['frames'])/seconds if seconds else 0,
                    rates=[(v-a)/seconds if seconds else 0 for v,a in zip(row['rising'],self.first['rising'])],
                    max_gap_ms=row['max_gap']/75000.,received_at=now)

class SignalDma:
    def __init__(self,dma,core,allocate,clock=time.monotonic,pause=time.sleep):
        if core.read(0)!=0x53494731:raise RuntimeError('signal hardware ID mismatch')
        self.dma=dma;self.core=core;self.allocate=allocate;self.clock=clock;self.pause=pause
        self.leases=[];self.failed=False;self.channels=1
    def configure(self,coefficient=16384,channels=1,window=50,bypass=False):
        if self.leases:raise RuntimeError('DMA still owns buffers')
        if not 0<=coefficient<=65536 or not 1<=channels<=8 or not 1<=window<=65535:raise ValueError('invalid signal settings')
        self.channels=channels
        for addr,value in ((8,coefficient),(12,channels),(16,window),(4,1|(2 if bypass else 0))):self.core.write(addr,value)
    def reset(self,timeout=.2):
        for addr in (0,0x30):self.dma.write(addr,4)
        deadline=self.clock()+timeout
        while self.clock()<deadline:
            if all(self.dma.read(a)&4==0 and self.dma.read(a+4)&1 for a in (0,0x30)):
                for buf in self.leases:buf.freebuffer()
                self.leases=[];return True
            self.pause(.001)
        _QUARANTINED.extend(self.leases);self.leases=[];self.failed=True;return False
    def process(self,samples,timeout=1):
        if self.failed:raise RuntimeError('DMA reset failed; board reboot required')
        if not samples or len(samples)%self.channels or len(samples)>65536 or any(type(v) is not int or not -2**31<=v<2**31 for v in samples):raise ValueError('signed interleaved sample block required')
        tx=self.allocate(shape=(len(samples),),dtype='int32');self.leases.append(tx)
        try:
            rx=self.allocate(shape=(len(samples),),dtype='int32');self.leases.append(rx)
            tx[:]=samples;tx.flush()
            if tx.physical_address>=2**32 or rx.physical_address>=2**32:raise RuntimeError('DMA address outside Zynq DDR')
            for a in (4,0x34):self.dma.write(a,0x7000)
            for a in (0,0x30):self.dma.write(a,1)
            self.dma.write(0x48,rx.physical_address);self.dma.write(0x58,len(samples)*4)
            self.dma.write(0x18,tx.physical_address);self.dma.write(0x28,len(samples)*4)
            deadline=self.clock()+timeout
            while True:
                statuses=[self.dma.read(a) for a in (4,0x34)]
                if any(v&0x770 for v in statuses):raise RuntimeError('signal DMA error')
                if all(v&2 for v in statuses):break
                if self.clock()>=deadline:raise TimeoutError('signal DMA timeout')
                self.pause(.001)
            rx.invalidate();output=[int(v) for v in rx]
            for buf in self.leases:buf.freebuffer()
            self.leases=[];return output
        except BaseException:
            self.reset();raise
    def stats(self,channel=0):
        if self.leases:raise RuntimeError('statistics require stopped transfer')
        self.core.write(0x14,channel)
        total=self.core.read(0x24)|(self.core.read(0x28)<<32)
        if total&2**63:total-=2**64
        squares=self.core.read(0x2c)|(self.core.read(0x30)<<32)
        return dict(windows=self.core.read(0x20),sum=total,squares=squares,saturations=self.core.read(0x1c))
    def close(self):return self.reset()

class Stimulus:
    def __init__(self,mmio):
        if mmio.read(0)!=0x4f534438:raise RuntimeError('display hardware ID mismatch')
        self.mmio=mmio;self.last=-1.;self.witness=DisplayWitness()
    def tick(self,epoch,enabled,now):
        if now-self.last<.25:return None
        if self.mmio.read(4)&1:return None
        values=[self.mmio.read(128+i*4) for i in range(9)]
        result=self.witness.observe(dict(epoch=values[0],frames=values[1],ticks=values[2],max_gap=values[3],rising=values[4:8],active=bool(values[8])),now)
        self.mmio.write(60,epoch);self.mmio.write(124,int(enabled));self.mmio.write(8,1);self.last=now
        return result

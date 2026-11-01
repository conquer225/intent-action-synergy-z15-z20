"""CMA/AXI adapter for the generated HLS register ABI; timeout retains DMA buffers."""
import time
import cv2
import numpy as np
from .session import MODES

REGISTERS={'input_pixels':0x18,'output_pixels':0x24,'history':0x30,
           'width':0x3c,'height':0x44,'mode':0x4c,'reset_history':0x54,'threshold':0x5c}


class PLProcessor:
    def __init__(self,overlay,allocator=None,width=320,height=180):
        if allocator is None:
            from pynq import allocate
            allocator=allocate
        if overlay.ip_dict.get('vision_core_0',{}).get('phys_addr')!=0x43c30000:
            raise RuntimeError('Vision HWH address mismatch')
        self.ip=overlay.vision_core_0;self.width=width;self.height=height
        self.backend='PL HLS vision_core / %dx%d'%(width,height)
        self.buffers=[];self.running=False
        try:
            for _ in range(3):
                b=allocator(shape=(height,width),dtype=np.uint32);b[:]=0;b.flush();self.buffers.append(b)
            for name,b in zip(('input_pixels','output_pixels','history'),self.buffers):
                address=int(b.physical_address)
                if address<=0 or address+b.nbytes>0x40000000:raise RuntimeError('CMA outside mapped DDR')
                self.ip.write(REGISTERS[name],address);self.ip.write(REGISTERS[name]+4,0)
            self.ip.write(REGISTERS['width'],width);self.ip.write(REGISTERS['height'],height)
            self.ip.write(REGISTERS['threshold'],127)
        except BaseException:
            self.close();raise

    def process(self,rgb,mode,reset=False):
        if self.running:raise RuntimeError('Vision core still owns the previous buffers')
        if mode not in dict(MODES):raise ValueError('Unknown image mode')
        image=cv2.resize(rgb,(self.width,self.height),interpolation=cv2.INTER_AREA).astype(np.uint32)
        self.buffers[0][:]=(image[...,0]<<16)|(image[...,1]<<8)|image[...,2]
        self.buffers[0].flush()
        self.ip.write(REGISTERS['mode'],[m[0] for m in MODES].index(mode))
        self.ip.write(REGISTERS['reset_history'],int(reset))
        self.ip.read(0)  # Drain an old clear-on-read completion before this launch.
        self.running=True;self.ip.write(0,1);deadline=time.monotonic()+2
        while not self.ip.read(0)&2:
            if time.monotonic()>deadline:raise RuntimeError('PL processing timeout; buffers retained')
            time.sleep(.001)
        self.running=False
        if self.ip.read(0x10):raise RuntimeError('PL rejected image parameters')
        self.buffers[1].invalidate();out=np.asarray(self.buffers[1])
        rgb=np.stack(((out>>16)&255,(out>>8)&255,out&255),axis=-1).astype(np.uint8)
        return rgb

    def close(self,pl_reset=False):
        if self.running and not pl_reset:raise RuntimeError('Reset PL before freeing in-flight vision buffers')
        for b in self.buffers:b.freebuffer()
        self.buffers=[];self.running=False

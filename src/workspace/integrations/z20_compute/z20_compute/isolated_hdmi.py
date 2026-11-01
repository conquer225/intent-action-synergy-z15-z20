"""MM2S-only overlay owner with a separate boot-reserved display ring."""
import mmap
import os
from pathlib import Path
import struct
import time

from .fixed_scene_hdmi import _uio,_read,_write,display_plan,FRAME_BYTES

DISPLAY_BASE=0x04000000
DISPLAY_SIZE=3*FRAME_BYTES


class OverlayDisplay:
    """Injectable register adapters and reserved display buffer; camera DMA stays running."""
    def __init__(self,control,vtc,pixels):
        if len(pixels)!=DISPLAY_SIZE:raise ValueError('expected isolated three-frame ring')
        self.control,self.vtc,self.pixels=control,vtc,pixels
        self.started=False

    def show(self,frame):
        if len(frame)!=FRAME_BYTES:raise ValueError('expected RGB720p frame')
        c,v=self.control,self.vtc
        if not self.started:
            c.write(0x20000,c.read(0x20000)&~1)
            deadline=time.monotonic()+1
            while not c.read(0x20004)&1:
                if time.monotonic()>deadline:raise TimeoutError('display MM2S did not halt')
                time.sleep(.002)
            v.write(0,v.read(0)&~4)
            c.write(0x20000,4)
            deadline=time.monotonic()+1
            while c.read(0x20000)&4:
                if time.monotonic()>deadline:raise TimeoutError('display MM2S reset timed out')
                time.sleep(.002)
            for i in range(3):
                self.pixels[i*FRAME_BYTES:(i+1)*FRAME_BYTES]=frame
                c.write(0x2005c+4*i,DISPLAY_BASE+i*FRAME_BYTES)
            c.write(0x20004,0xfff0)
            c.write(0x20058,3840);c.write(0x20054,3840);c.write(0x20028,0)
            for offset,value in display_plan()['vtc'].items():v.write(offset,value)
            v.write(0,display_plan()['vtc_control'])
            c.write(0x20000,1)  # Park, no genlock dependency on the camera ring.
            c.write(0x20050,720)
            self.started=True
        else:
            active=(c.read(0x20028)>>16)&31
            if active>=3:raise RuntimeError('unexpected active display frame')
            slot=(active+1)%3
            self.pixels[slot*FRAME_BYTES:(slot+1)*FRAME_BYTES]=frame
            c.write(0x20028,slot)
            deadline=time.monotonic()+.5
            while (c.read(0x20028)>>16)&31!=slot:
                if time.monotonic()>deadline:raise TimeoutError('display did not switch frame')
                time.sleep(.002)
        status=c.read(0x20004)
        if status&0xff0:raise RuntimeError('display VDMA error 0x{:08x}'.format(status))
        return status

    def readback(self):
        if not self.started:
            raise RuntimeError('display has not started')
        slot = (self.control.read(0x20028) >> 16) & 31
        if slot >= 3:
            raise RuntimeError('unexpected active display frame')
        return bytes(self.pixels[slot*FRAME_BYTES:(slot+1)*FRAME_BYTES])


class _MappedRegisters:
    def __init__(self,mapping):self.mapping=mapping
    def read(self,offset):return _read(self.mapping,offset)
    def write(self,offset,value):_write(self.mapping,offset,value)


class NavigatorOverlay:
    """Requires the camera-demo DTB with observer map2 and display@4000000."""
    def __init__(self):
        control=_uio('navigator-vdma-control',0x43000000,0x30000)
        observer=_uio('z20-video-observer',0x43c20000,0x10000)
        info=observer/'maps/map2'
        reserve=Path('/proc/device-tree/reserved-memory/display@4000000')
        if (not info.exists() or not reserve.exists()
                or int((info/'addr').read_text(),0)!=DISPLAY_BASE
                or int((info/'size').read_text(),0)!=DISPLAY_SIZE
                or int((info/'offset').read_text(),0)!=0
                or (reserve/'reg').read_bytes()!=struct.pack('>II',DISPLAY_BASE,DISPLAY_SIZE)
                or not (reserve/'no-map').exists()):
            raise ValueError('load the camera-demo DTB with isolated display reservation')
        self.fds=[];self.maps=[]
        try:
            for device,size,offset in (('/dev/'+control.name,0x30000,0),
                    ('/dev/'+observer.name,DISPLAY_SIZE,2*mmap.PAGESIZE),
                    ('/dev/mem',mmap.PAGESIZE,0x43c10000)):
                fd=os.open(device,os.O_RDWR|os.O_SYNC);self.fds.append(fd)
                self.maps.append(mmap.mmap(fd,size,access=mmap.ACCESS_WRITE,offset=offset))
            self.display=OverlayDisplay(_MappedRegisters(self.maps[0]),
                                        _MappedRegisters(self.maps[2]),self.maps[1])
        except BaseException:self.close();raise

    def show(self,frame):return self.display.show(frame)

    def readback(self):return self.display.readback()

    def close(self):
        for m in reversed(self.maps):m.close()
        for fd in reversed(self.fds):os.close(fd)
        self.maps=[];self.fds=[]

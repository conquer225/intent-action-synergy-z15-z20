"""Explicit camera adapters. No camera substitution or prerecorded fallback."""
import ctypes as C
import os
from pathlib import Path
import time
import numpy as np
from PIL import Image
from .session import Frame


class PgmSource:
    """Read atomic PGM publications from the existing Tobii USB owner."""
    def __init__(self,directory,generation):
        self.directory=Path(directory)
        self.generation=generation
        self.seen={p.name:p.stat().st_mtime_ns for p in self.directory.glob('*.pgm')}
        self.sequence=0

    def read(self,now):
        choices=[]
        for path in self.directory.glob('*.pgm'):
            if path.is_symlink():continue
            stat=path.stat()
            if stat.st_mtime_ns!=self.seen.get(path.name) and 0<=time.time_ns()-stat.st_mtime_ns<=1500000000:
                choices.append((stat.st_mtime_ns,path))
        if not choices:return None
        stamp,path=max(choices)
        if path.stat().st_size>1920*1080+256:raise ValueError('Oversized Tobii image')
        with Image.open(path) as image:
            if image.format!='PPM' or image.mode!='L' or image.width>1920 or image.height>1080:
                raise ValueError('Expected bounded grayscale PGM')
            rgb=np.array(image.convert('RGB'))
        # Atomic rename prevents partial reads; recheck if the ring changed again.
        if path.stat().st_mtime_ns!=stamp:return None
        self.seen[path.name]=stamp;self.sequence+=1
        captured=now-max(0,(time.time_ns()-stamp)/1e9)
        return Frame('tobii',self.generation,self.sequence,captured,rgb)

    def close(self):pass


class CaptureCleanupError(RuntimeError):
    def __init__(self,owner):
        super().__init__('Capture DMA did not halt; retain CMA until PL reset')
        self.owner=owner


class OV5640Source:
    """Own only VDMA1 capture and SCCB; never initializes or stops the HDMI DMA."""
    def __init__(self,library,generation,allocator=None):
        if allocator is None:
            from pynq import allocate
            allocator=allocate
        self.generation=generation;self.sequence=0;self.buffers=[];self.opened=False
        self.lib=C.CDLL(str(library))
        self.lib.vision_camera_open.argtypes=[C.c_uint32,C.c_uint32]
        self.lib.vision_camera_open.restype=C.c_int
        self.lib.vision_camera_next.restype=C.c_int
        self.lib.vision_camera_close.restype=C.c_int
        self.lib.vision_camera_forget.restype=None
        try:
            for _ in range(2):
                b=allocator(shape=(720,1280,3),dtype=np.uint8)
                b[:]=0;b.flush();self.buffers.append(b)
            if not self.lib.vision_camera_open(*[int(b.physical_address) for b in self.buffers]):
                raise RuntimeError('OV5640 capture initialization failed')
            self.opened=True
        except BaseException:
            try:self.close()
            except RuntimeError:raise CaptureCleanupError(self)
            raise

    def read(self,now):
        index=self.lib.vision_camera_next()
        if index not in (0,1):raise RuntimeError('OV5640 frame timeout')
        self.buffers[index].invalidate()
        bgr=np.array(self.buffers[index],copy=True,subok=False)
        self.sequence+=1
        return Frame('ov5640',self.generation,self.sequence,time.monotonic(),bgr[...,::-1].copy())

    def close(self):
        if self.buffers:
            if not self.lib.vision_camera_close():
                raise RuntimeError('Capture DMA did not halt; retain CMA until PL reset')
            self.opened=False
            for b in self.buffers:b.freebuffer()
            self.buffers=[]

    def release_after_reset(self):
        """Call only after the owner has verified a replacement PL overlay."""
        self.lib.vision_camera_forget()
        for b in self.buffers:b.freebuffer()
        self.buffers=[];self.opened=False

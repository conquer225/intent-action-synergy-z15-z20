"""Autonomous video: CPU configures a ring and mode, never presents camera frames."""
import ctypes as C
import time
import numpy as np


class CameraStartError(RuntimeError):
    """Camera admission failed; start() rethrows only after verified cleanup."""


class ContinuousVideo:
    def __init__(self,registers,library,allocator=None,native=None,now=time.monotonic,sleep=time.sleep):
        if registers.read(0)!=0x56495332:raise RuntimeError('Expected VIS2 streaming hardware')
        self.ip=registers;self.library=library;self.allocator=allocator;self.native=native
        self.now=now;self.sleep=sleep;self.buffers=[];self.active=False;self.mode=0
        self.sample=None;self.rates={};self.last_camera=None;self.last_progress=None
        self.last_display=None;self.last_display_progress=None
        self.pending_config=None;self.config_requested_at=None
        if self.native is None:
            self.native=C.CDLL(str(library))
            self.native.vision_live_open.argtypes=[C.POINTER(C.c_uint32)]
            self.native.vision_live_open.restype=C.c_int
            self.native.vision_live_close.restype=C.c_int
            self.native.vision_live_health.restype=C.c_int
            self.native.vision_live_forget.restype=None

    def start(self,mode):
        self.select(mode)
        if self.active:return
        if self.buffers:raise RuntimeError('Previous DMA ownership unresolved; retain memory')
        allocator=self.allocator
        if allocator is None:
            from pynq import allocate
            allocator=allocate
        try:
            for _ in range(3):
                b=allocator(shape=(720,1280,3),dtype=np.uint8)
                self.buffers.append(b);b[:]=0;b.flush()
            physical=[int(b.physical_address) for b in self.buffers]
            for address,b in zip(physical,self.buffers):
                if address<=0 or address&7 or address+b.nbytes>0x40000000:
                    raise ValueError('Live CMA must fit mapped DDR before uint32 conversion')
            addresses=(C.c_uint32*3)(*physical)
            if not self.native.vision_live_open(addresses):raise CameraStartError('Autonomous OV5640 ring failed to start')
            self.active=True;self.last_progress=self.now();self.last_camera=self.ip.read(0x10)
            self.last_display=self.ip.read(0x0c);self.last_display_progress=self.now()
            self.sample=None;self.rates={};self.service()
        except BaseException:
            self.close();raise

    def select(self,mode):
        if type(mode) is not int or not 0<=mode<=8:raise ValueError('OV5640 streaming mode must be 0..8')
        self.mode=mode

    def _configure(self,value,wait=False):
        if self.pending_config!=value:
            self.pending_config=value;self.config_requested_at=self.now()
        while True:
            busy=self.ip.read(8)
            applied=self.ip.read(4)
            if not busy:
                if applied==value:
                    self.pending_config=None;self.config_requested_at=None;return True
                self.ip.write(4,value)
            if self.now()-self.config_requested_at>.6:
                raise RuntimeError('Streaming mode frame acknowledgment timed out')
            if not wait:return False
            self.sleep(.002)

    def service(self):
        if not self.active:return
        if not self.native.vision_live_health():raise RuntimeError('Autonomous video DMA fault; retain ring until cleanup')
        self._configure(0x10|self.mode)
        now=self.now();camera=self.ip.read(0x10);display=self.ip.read(0x0c);pixels=self.ip.read(0x14)
        if camera!=self.last_camera:self.last_camera=camera;self.last_progress=now
        if now-self.last_progress>1.5:raise RuntimeError('OV5640 input stopped updating')
        if display!=self.last_display:self.last_display=display;self.last_display_progress=now
        if now-self.last_display_progress>1.5:raise RuntimeError('HDMI output stopped updating')
        if self.sample and now-self.sample[0]>=.5:
            previous=self.sample;period=now-previous[0]
            self.rates=dict(camera_fps=((camera-previous[1])&0xffffffff)/period,
                hdmi_hz=((display-previous[2])&0xffffffff)/period,
                filter_pixels_per_second=((pixels-previous[3])&0xffffffff)/period)
            self.sample=(now,camera,display,pixels)
        elif self.sample is None:self.sample=(now,camera,display,pixels)

    def snapshot(self):
        return dict(architecture='continuous_native_stream',source_resolution=[1280,720],
                    processing_backend='PL pixel pipeline / 1280x720',ps_frame_submission=False,
                    frame_sequence=self.last_camera,age_seconds=self.now()-self.last_progress if self.last_progress else None,
                    **self.rates)

    def close(self,pl_reset=False):
        if not self.buffers:return
        if pl_reset:self.native.vision_live_forget()
        else:
            config_error=None
            try:
                if self.active:self._configure(0,wait=True)
            except RuntimeError as exc:config_error=exc
            if not self.native.vision_live_close():raise RuntimeError('Live DMA did not halt; retain all ring memory until PL reset')
            if config_error:raise config_error
        self.active=False
        for b in self.buffers:b.freebuffer()
        self.buffers=[];self.sample=None;self.rates={};self.last_camera=None;self.last_progress=None
        self.last_display=None;self.last_display_progress=None
        self.pending_config=None;self.config_requested_at=None

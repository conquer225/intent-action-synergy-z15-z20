"""One display/PL owner, original ARM acquisition guard, explicit recovery."""
import ctypes as C,json,time
from pathlib import Path
from contextlib import ExitStack
from . import vendor
from .board import SignalDma,Stimulus,_QUARANTINED

def framebuffer_pixels(image):
    import numpy as np
    if hasattr(image,'tobytes') and hasattr(image,'mode'):
        if image.size!=(1280,720) or image.mode!='RGB':raise ValueError('HDMI RGB page must be 1280x720')
        return np.frombuffer(image.tobytes('raw','BGR'),dtype=np.uint8).reshape((720,1280,3))
    if not isinstance(image,np.ndarray) or image.shape!=(720,1280,3) or image.dtype!=np.uint8:raise ValueError('original calibration frame must be BGR888')
    return image

class HdmiDisplay:
    def __init__(self,bit,eye_root):
        import fcntl,numpy as np
        from pynq import Overlay,PL,allocate,MMIO
        from coexist_guard import CoexistGuard,verify_release,BRAIN_ROOT
        self.stack=ExitStack();self.buffers=[];self.lib=None;self.mapped=False;self.overlay=None;self.original=PL.bitfile_name
        self.current=0;self.np=np;self.Overlay=Overlay;self.download_attempted=False
        self.guard=CoexistGuard(eye_root,self.original)
        try:
            for name in ('guardianloop-pl','tobii_display'):
                lock=self.stack.enter_context(open('/run/lock/'+name+'.lock','a'))
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if not self.original or not Path(self.original).is_file():raise RuntimeError('original overlay unavailable for recovery')
            verify_release(BRAIN_ROOT);self.guard.check_runtime()
            self.download_attempted=True;self.overlay=Overlay(str(bit),download=True)
            for name,address in [('axi_vdma_0',0x43000000),('axi_vdma_1',0x43010000),('live_osd_0',0x43c00000),('v_tc_0',0x43c10000),('axi_dma_signal',0x40400000),('signal_core_0',0x43c20000),('axi_gpio_keys',0x41210000)]:
                if self.overlay.ip_dict.get(name,{}).get('phys_addr')!=address:raise RuntimeError('overlay address mismatch: '+name)
            self.lib=C.CDLL(str(Path(eye_root)/'libtobii_display.so'))
            self.lib.display_open.argtypes=[C.POINTER(C.c_uint32)];self.lib.display_park.argtypes=[C.c_uint]
            self.lib.display_frames.restype=self.lib.display_status.restype=C.c_uint32
            self.signal=SignalDma(MMIO(0x40400000,65536),MMIO(0x43c20000,65536),allocate);self.signal.configure()
            self.stimulus=Stimulus(MMIO(0x43c00000,65536))
            from .controls import PlButtons
            self.buttons=PlButtons(MMIO(0x41210000,65536))
            for _ in range(3):
                buf=allocate(shape=(720,1280,3),dtype=np.uint8);self.buffers.append(buf);buf[:]=0;buf.flush()
                if buf.physical_address>=2**32:raise RuntimeError('framebuffer address outside DDR')
            self.mapped=True
            if not self.lib.display_open((C.c_uint32*3)(*[b.physical_address for b in self.buffers])):raise RuntimeError('HDMI initialization failed')
            self.last_frames=self.lib.display_frames();self.progress=time.monotonic();self.checked=0
        except BaseException:self.close();raise
    def present(self,image,now):
        if now-self.checked>1:
            self.guard.check_runtime();self.checked=now
        next_index=(self.current+1)%3
        self.buffers[next_index][:]=framebuffer_pixels(image);self.buffers[next_index].flush()
        if not self.lib.display_park(next_index):raise RuntimeError('framebuffer park failed')
        self.current=next_index;count=self.lib.display_frames()
        if self.lib.display_status()&0xff1:raise RuntimeError('HDMI DMA fault')
        if count!=self.last_frames:self.progress=now;self.last_frames=count
        elif now-self.progress>2:raise RuntimeError('HDMI frame counter stalled')
    def close(self):
        try:
            if hasattr(self,'signal'):self.signal.close()
            halted=self.lib.display_close() if self.mapped and self.lib else True
            if self.download_attempted and self.original:
                # A PL reconfiguration quiesces both DMA engines before buffer release.
                self.Overlay(self.original,download=True)
                halted=True
            if halted:
                for buf in self.buffers:buf.freebuffer()
                self.buffers=[]
                for buf in _QUARANTINED:buf.freebuffer()
                _QUARANTINED.clear()
            else:
                _QUARANTINED.extend(self.buffers);self.buffers=[]
                raise RuntimeError('HDMI did not halt; buffers retained, reboot required')
        except BaseException:
            _QUARANTINED.extend(self.buffers);self.buffers=[]
            raise
        finally:self.stack.close()

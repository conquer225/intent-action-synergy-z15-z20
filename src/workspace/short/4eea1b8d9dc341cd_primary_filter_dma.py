"""Register-model-only simple-DMA backend; never use with physical DMA.

The former pynq.allocate path has no verified cross-process buffer lifetime.
Physical use is disabled until a kernel-owned buffer lease and observable
PS/HP recovery are implemented and verified. test_only=True is for isolated
register-model tests; it does not confer hardware safety.
"""
import time
import numpy as np

SIGNATURE = 0x50460000
STATUS_MASK = 0xfffffffc
FRAME_BYTES = 640
ERRORS = 0x770
IOC = 0x1000
_quarantined = {}  # In-process test only; not a crash-safe physical pin.


class PrimaryFilterDMA:
    def __init__(self, dma, control, allocate, parameters, timeout=.1,
                 clock=time.monotonic, sleep=time.sleep, *, test_only=False):
        if not test_only:
            raise RuntimeError(
                'Physical DMA disabled: buffer lifetime after process death is unverified; '
                'a kernel-owned lease and verified PS/HP recovery are required'
            )
        expected = {'c_include_mm2s':1,'c_include_s2mm':1,'c_include_sg':0,
                    'c_m_axis_mm2s_tdata_width':64,'c_s_axis_s2mm_tdata_width':64,
                    'c_addr_width':32}
        normalized = {k.lower():int(v) for k,v in parameters.items() if k.lower() in expected}
        if normalized != expected:
            raise ValueError('Requires candidate 64-bit bidirectional simple DMA, 32-bit addresses')
        if timeout <= 0 or not np.isfinite(timeout):
            raise ValueError('Positive finite timeout required')
        self.dma, self.control = dma, control
        self.clock, self.sleep, self.timeout = clock, sleep, float(timeout)
        self.ready = False
        self.closed = False
        self.bus_ownership_uncertain = False
        self.origin = None
        self._check_signature()
        self.tx = allocate(shape=(80,), dtype=np.int64)
        try:
            self.rx = allocate(shape=(80,), dtype=np.int64)
        except BaseException:
            self.tx.freebuffer()
            raise
        for buf in (self.tx,self.rx):
            if buf.shape != (80,) or buf.dtype != np.int64 or buf.nbytes != FRAME_BYTES or not 0 <= int(buf.physical_address) <= 2**32-FRAME_BYTES or int(buf.physical_address)%8:
                self.tx.freebuffer();self.rx.freebuffer()
                raise ValueError('DMA buffer size/alignment/address invalid')

    def _check_signature(self):
        status = self.control.read(0x08)
        if status & STATUS_MASK != SIGNATURE:
            self.ready = False
            raise RuntimeError('Wrong filter control signature/ABI')
        return status

    def _poll(self, predicate, label):
        end = self.clock()+self.timeout
        while not predicate():
            if self.clock() >= end:
                raise TimeoutError(label)
            self.sleep(.00001)

    def _quiesce(self):
        self.ready = False
        # If reset or halt times out, retain both buffers and forbid retry.
        # A successful quiesce is called only outside an uncertain transfer;
        # DMA halt is not a proof that HP0 has drained a previous fault.
        _quarantined[id(self)] = self
        self.bus_ownership_uncertain = True
        self.dma.write(0x00,4)
        self._poll(lambda:not (self.dma.read(0x00)&4 or self.dma.read(0x30)&4), 'DMA reset timeout')
        self._poll(lambda:bool(self.dma.read(0x04)&1 and self.dma.read(0x34)&1), 'DMA halt timeout')
        self.bus_ownership_uncertain = False
        _quarantined.pop(id(self),None)

    def reset(self):
        if self.closed:
            raise RuntimeError('Backend is closed')
        if self.bus_ownership_uncertain:
            raise RuntimeError('In-flight AXI ownership unknown; keep DMA buffers pinned and restart PS/HP before reuse')
        self._quiesce()
        self.control.write(0x04,0)  # GPIO channel 1 output directions
        self.control.write(0x0c,0xffffffff)  # Channel 2 status inputs
        self.control.write(0x00,1)
        self._poll(lambda:bool(self._check_signature()&1), 'Filter reset assertion timeout')
        self.control.write(0x00,0)
        self._poll(lambda:self._check_signature()==SIGNATURE, 'Filter reset release timeout')
        self.origin = None
        self.dma.write(0x00,1)
        self.dma.write(0x30,1)
        self._poll(lambda:not (self.dma.read(0x04)&1 or self.dma.read(0x34)&1), 'DMA start timeout')
        self.ready = True

    def process(self, samples_uv):
        if not self.ready or self.closed:
            raise RuntimeError('Reset/re-warmup required before a new batch')
        raw = np.asarray(samples_uv,dtype=np.float64)
        if raw.shape != (10,8) or not np.isfinite(raw).all():
            raise ValueError('Exactly ten finite eight-channel samples required')
        origin = raw[0].copy() if self.origin is None else self.origin
        scaled = (raw-origin)*65536
        packed = np.copysign(np.floor(np.abs(scaled)+.5),scaled)
        if np.any(packed < -(1<<39)) or np.any(packed > (1<<39)-1):
            raise OverflowError('Input outside signed40/16 contract')
        if self._check_signature() != SIGNATURE:
            self.ready = False
            raise RuntimeError('Filter is reset or faulted')
        self.tx[:] = packed.astype(np.int64).reshape(-1)
        self.tx.flush()
        # No CPU writes to RX between transfer start and completion.
        self.rx.flush()
        _quarantined[id(self)] = self
        self.ready = False
        self.bus_ownership_uncertain = True
        # Any exception below leaves the buffers pinned; PL reset alone does not
        # prove that the PS-side AXI burst has completed or been cancelled.
        self.dma.write(0x04,0x7000)
        self.dma.write(0x34,0x7000)
        self.dma.write(0x48,int(self.rx.physical_address))
        self.dma.write(0x4c,0)
        self.dma.write(0x58,FRAME_BYTES)  # Arm S2MM before MM2S.
        self.dma.write(0x18,int(self.tx.physical_address))
        self.dma.write(0x1c,0)
        self.dma.write(0x28,FRAME_BYTES)
        def done():
            a,b = self.dma.read(0x04),self.dma.read(0x34)
            if (a|b)&ERRORS or self._check_signature()!=SIGNATURE:
                raise RuntimeError('DMA/filter fault; reject entire batch')
            if (a|b)&1:
                raise RuntimeError('DMA halted during batch')
            return bool(a&IOC and b&IOC and a&2 and b&2)
        self._poll(done,'DMA frame timeout; reject entire batch')
        if self.dma.read(0x58)!=FRAME_BYTES:
            raise RuntimeError('Incomplete S2MM frame')
        self.rx.invalidate()
        values = np.asarray(self.rx,dtype=np.int64)
        if np.any(values < -(1<<39)) or np.any(values > (1<<39)-1):
            raise RuntimeError('Invalid returned sign extension')
        result = values.reshape(10,8).astype(np.float64)/65536
        _quarantined.pop(id(self),None)
        self.bus_ownership_uncertain = False
        self.origin = origin
        self.ready = True
        return result

    def close(self):
        if self.closed:
            return
        if self.bus_ownership_uncertain:
            raise RuntimeError('In-flight AXI ownership unknown; DMA buffers remain pinned until PS/HP restart')
        self._quiesce()  # Failure intentionally retains buffers and raises.
        self.control.write(0x00,1)
        self.tx.freebuffer();self.rx.freebuffer()
        self.closed = True

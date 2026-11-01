"""HLS memory-master adapter; allocation and MMIO are injected for ARM/host use."""
import threading
import time
import numpy as np

# From the generated xz20_mlp_hw.h, Vitis HLS 2023.1. No board base address here.
POINTERS = (0x18, 0x24, 0x30, 0x3c, 0x48, 0x54)


class HardwareNPU:
    name = "PL_z20_mlp"

    def __init__(self, registers, allocate, *, timeout=.5, now=time.monotonic, sleep=time.sleep):
        self.registers, self.allocate, self.timeout = registers, allocate, timeout
        self.now, self.sleep = now, sleep
        self.lock = threading.Lock()
        self.buffers = []
        self.poisoned = False
        self.last_timing = {}

    def _allocate(self):
        try:
            for shape, dtype in [((1024,), np.int8), ((32*1024,), np.int8), ((32,), np.int32),
                                 ((96,), np.int8), ((3,), np.int32), ((3,), np.int32)]:
                buffer = self.allocate(shape=shape, dtype=dtype)
                self.buffers.append(buffer)
                address = int(buffer.physical_address)
                if address <= 0 or address % 8 or address+buffer.nbytes > 2**32:
                    raise ValueError("DMA buffer must fit aligned Zynq-7000 physical address space")
        except BaseException:
            for buffer in self.buffers:
                buffer.freebuffer()
            self.buffers.clear()
            raise

    def infer(self, model, values):
        values = np.asarray(values)
        if values.dtype != np.int8 or values.shape != (model.w1.shape[1],):
            raise ValueError("input differs from model contract")
        with self.lock:
            if self.poisoned:
                raise RuntimeError("NPU ownership unresolved after timeout; verified reset required")
            if not self.registers.read(0) & 4:
                raise RuntimeError("NPU is not idle")
            start = self.now()
            if not self.buffers:
                self._allocate()
            arrays = [values, model.w1.reshape(-1), model.b1, model.w2.reshape(-1), model.b2,
                      np.zeros(3, dtype=np.int32)]
            for buffer, source, offset in zip(self.buffers, arrays, POINTERS):
                buffer[:len(source)] = source
                buffer.flush()
                address = int(buffer.physical_address)
                self.registers.write(offset, address & 0xffffffff)
                self.registers.write(offset+4, address >> 32)
            self.registers.write(0x60, len(values))
            self.registers.write(0x68, model.hidden_shift)
            launched = self.now()
            try:
                self.registers.write(0, 1)
                while not self.registers.read(0) & 2:
                    if self.now()-launched > self.timeout:
                        raise TimeoutError("NPU timed out; buffers retained until verified PL reset")
                    self.sleep(.0001)
            except BaseException:
                self.poisoned = True
                raise
            if self.registers.read(0x10) != 0:
                raise ValueError("NPU rejected dimensions or accumulator overflow")
            self.buffers[-1].invalidate()
            output = np.array(self.buffers[-1], dtype=np.int32, copy=True)
            self.last_timing = dict(total_seconds=self.now()-start, launch_to_done_seconds=self.now()-launched,
                                    scope="PS buffer copies, cache operations, MMIO and HLS memory-master transaction")
            return output

    def close(self, *, pl_reset_verified=False):
        with self.lock:
            if self.poisoned and not pl_reset_verified:
                raise RuntimeError("cannot free DMA memory while a timed-out accelerator may access it")
            if self.buffers and not pl_reset_verified and not self.registers.read(0) & 4:
                raise RuntimeError("NPU still owns DMA buffers")
            for buffer in self.buffers:
                buffer.freebuffer()
            self.buffers.clear()
            self.poisoned = False

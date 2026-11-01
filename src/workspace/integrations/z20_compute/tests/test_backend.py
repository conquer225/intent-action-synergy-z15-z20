import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.backend import HardwareNPU
from test_npu import worked_model


class Buffer(np.ndarray):
    def __new__(cls, shape, dtype, address):
        obj = np.zeros(shape, dtype=dtype).view(cls)
        obj.physical_address, obj.freed, obj.flushed, obj.invalidated = address, False, False, False
        return obj
    def flush(self): self.flushed = True
    def invalidate(self): self.invalidated = True
    def freebuffer(self): self.freed = True


class BackendTests(unittest.TestCase):
    def test_lost_mmio_after_start_preserves_memory_and_requires_reset(self):
        buffers = []
        class Registers:
            started = False
            def read(self, offset):
                if self.started: raise OSError("MMIO transport lost")
                return 4
            def write(self, offset, value):
                if offset == 0: self.started = True
        def allocate(shape, dtype):
            buffer = Buffer(shape, dtype, 0x100000+len(buffers)*0x10000)
            buffers.append(buffer)
            return buffer
        backend = HardwareNPU(Registers(), allocate)
        with self.assertRaises(OSError): backend.infer(worked_model(), np.array([3, -2], np.int8))
        self.assertTrue(backend.poisoned)
        self.assertFalse(any(b.freed for b in buffers))
        backend.close(pl_reset_verified=True)

    def test_done_reads_result_and_timeout_retains_dma_ownership(self):
        buffers, clock = [], [0.]
        def allocate(shape, dtype):
            result = Buffer(shape, dtype, 0x100000 + len(buffers)*0x10000)
            buffers.append(result)
            return result
        class Registers:
            running = False
            hang = False
            def write(self, offset, value):
                if offset == 0 and value == 1:
                    self.running = True
                    if not self.hang:
                        buffers[-1][:] = [3, 125, -3]
            def read(self, offset):
                if offset == 0:
                    return 0 if self.running and self.hang else 6
                return 0
        regs = Registers()
        backend = HardwareNPU(regs, allocate, now=lambda: clock[0],
                              sleep=lambda seconds: clock.__setitem__(0, clock[0]+seconds), timeout=.01)
        values = np.array([3, -2], dtype=np.int8)
        self.assertEqual(backend.infer(worked_model(), values).tolist(), [3, 125, -3])
        self.assertTrue(all(b.flushed for b in buffers))
        self.assertTrue(buffers[-1].invalidated)
        regs.running = False
        regs.hang = True
        with self.assertRaises(TimeoutError): backend.infer(worked_model(), values)
        self.assertFalse(any(b.freed for b in buffers))
        with self.assertRaises(RuntimeError): backend.infer(worked_model(), values)
        with self.assertRaises(RuntimeError): backend.close()
        backend.close(pl_reset_verified=True)
        self.assertTrue(all(b.freed for b in buffers))


if __name__ == "__main__": unittest.main()

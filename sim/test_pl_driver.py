"""MMIO/cache/ownership behavior at the actual PS driver interface."""
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/workspace/integrations'))
from pl_accel.backend import MemoryKernel


class Buffer(np.ndarray):
    def __new__(cls, size, address, events):
        value = np.zeros(size, np.int32).view(cls)
        value.physical_address, value.events, value.freed = address, events, False
        return value
    def flush(self):self.events.append(('flush', self.physical_address))
    def invalidate(self):self.events.append(('invalidate', self.physical_address))
    def freebuffer(self):self.freed = True


class Hardware:
    def __init__(self, timeout=False):
        self.events, self.buffers, self.words, self.timeout = [], [], {}, timeout
        self.ticks = 0
    def allocate(self, *, shape, dtype):
        value = Buffer(shape[0], 0x06000000+len(self.buffers)*4096, self.events)
        self.buffers.append(value);return value
    def read(self, offset):
        if offset == 0:return 1 if self.timeout and self.words.get(0) else 6
        return self.words.get(offset, 0)
    def write(self, offset, value):
        self.events.append(('write', offset, value));self.words[offset] = value
        if offset == 0 and value == 1 and not self.timeout:self.buffers[1][:] = [17, -23]
    def now(self):self.ticks += .1;return self.ticks


class DriverContract(unittest.TestCase):
    def create(self, hw):
        return MemoryKernel(hw, hw.allocate, {'input': (0x10, 4), 'output': (0x20, 2)},
                            timeout=.2, now=hw.now, sleep=lambda _: None)

    def test_addresses_cache_and_owned_output(self):
        hw = Hardware();driver = self.create(hw)
        result = driver.invoke({'input': np.array([1, 2, 3, 4], np.int32)}, outputs=('output',))
        np.testing.assert_array_equal(result['output'], [17, -23])
        self.assertEqual(hw.words[0x10], 0x06000000)
        self.assertEqual(hw.words[0x14], 0)
        start = hw.events.index(('write', 0, 1))
        self.assertLess(hw.events.index(('flush', 0x06000000)), start)
        self.assertGreater(hw.events.index(('invalidate', 0x06001000)), start)
        hw.buffers[1][:] = 0
        np.testing.assert_array_equal(result['output'], [17, -23])
        driver.close();self.assertTrue(all(b.freed for b in hw.buffers))

    def test_unresolved_timeout_retains_memory_until_reset(self):
        hw = Hardware(timeout=True);driver = self.create(hw)
        with self.assertRaises(TimeoutError):
            driver.invoke({'input': np.zeros(4, np.int32)}, outputs=('output',))
        with self.assertRaises(RuntimeError):driver.close()
        self.assertFalse(any(b.freed for b in hw.buffers))
        driver.close(reset_verified=True)
        self.assertTrue(all(b.freed for b in hw.buffers))

    def test_hwh_metadata_selects_only_the_matching_z15_control_aperture(self):
        from pl_accel.metadata import eeg_aperture
        xml = '''<EDKSYSTEM><SYSTEMINFO DEVICE="7z015" PACKAGE="clg485"/>
        <MODULES><MODULE INSTANCE="z15_fbcsp_0" VLNV="xilinx.com:hls:z15_fbcsp:1.0"/></MODULES>
        <MEMRANGES><MEMRANGE INSTANCE="z15_fbcsp_0" SLAVEBUSINTERFACE="s_axi_control"
        BASEVALUE="0x83c50000" HIGHVALUE="0x83c5ffff"/></MEMRANGES></EDKSYSTEM>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'system.hwh';path.write_text(xml, encoding='utf-8')
            self.assertEqual(eeg_aperture(path, 'z15_fbcsp_0'),
                             dict(phys_addr=0x83c50000, addr_range=65536))
            path.write_text(xml.replace('clg485', 'clg400'), encoding='utf-8')
            with self.assertRaises(ValueError):eeg_aperture(path, 'z15_fbcsp_0')


if __name__ == '__main__':unittest.main()

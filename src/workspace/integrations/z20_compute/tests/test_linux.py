import struct
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.linux import UioRegisters, UdmaAllocator


class LinuxTests(unittest.TestCase):
    def test_reserved_uio_dma_pool_checks_boot_reservation_and_owns_disjoint_ranges(self):
        from z20_compute.linux import UioDmaAllocator
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            info = root/'map1'; info.mkdir()
            for name, value in [('addr', '0x02000000'), ('size', '4096'), ('offset', '0')]:
                (info/name).write_text(value)
            reservation = root/'reserved'; reservation.mkdir()
            (reservation/'reg').write_bytes(struct.pack('>II', 0x02000000, 4096))
            (reservation/'no-map').touch()
            device = root/'uio'; device.write_bytes(bytes(8192))
            pool = UioDmaAllocator(device, info, reservation)
            a = pool(shape=(3,), dtype=np.int32)
            b = pool(shape=(3,), dtype=np.int32)
            self.assertEqual((a.physical_address, b.physical_address), (0x02000000, 0x02000040))
            b[:] = [3, 125, -3]
            b.flush(); b.invalidate()
            self.assertEqual(device.read_bytes()[4096+64:4096+76], struct.pack('<3i', 3, 125, -3))
            with self.assertRaises(RuntimeError): pool.close()
            a.freebuffer(); b.freebuffer(); pool.close()
            (reservation/'reg').write_bytes(struct.pack('>II', 0x01000000, 4096))
            with self.assertRaises(ValueError): UioDmaAllocator(device, info, reservation)

    def test_real_mapped_pool_is_retained_after_npu_timeout(self):
        from z20_compute.backend import HardwareNPU
        from test_npu import worked_model
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in [('phys_addr', '0x10000000'), ('size', '65536'),
                                ('sync_for_device', ''), ('sync_for_cpu', '')]:
                (root/name).write_text(value)
            dev = root/'dma'; dev.write_bytes(bytes(65536))
            pool = UdmaAllocator(dev, root)
            class Registers:
                started = False
                def read(self, offset): return 0 if self.started else 4
                def write(self, offset, value):
                    if offset == 0: self.started = True
            npu = HardwareNPU(Registers(), pool, timeout=.001)
            with self.assertRaises(TimeoutError):
                npu.infer(worked_model(), np.array([3, -2], np.int8))
            with self.assertRaises(RuntimeError): npu.close()
            with self.assertRaises(RuntimeError): pool.close()
            npu.close(pl_reset_verified=True)
            pool.close()

    def test_dma_rejects_non_ddr_ranges_and_exhaustion_without_aliasing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in [('phys_addr', '0x40000000'), ('size', '64'),
                                ('sync_for_device', ''), ('sync_for_cpu', '')]:
                (root/name).write_text(value)
            dev = root/'dma'; dev.write_bytes(bytes(64))
            with self.assertRaises(ValueError): UdmaAllocator(dev, root)
            (root/'phys_addr').write_text('0x10000000')
            pool = UdmaAllocator(dev, root)
            b = pool(shape=(1,), dtype=np.int8)
            with self.assertRaises(MemoryError): pool(shape=(1,), dtype=np.int8)
            with self.assertRaises(ValueError): pool(shape=(1,), dtype=object)
            b.freebuffer(); pool.close()

    def test_cli_keeps_software_default_and_exposes_explicit_linux_devices(self):
        from z20_compute.__main__ import parser
        default = parser().parse_args(['serve', '--models', 'models'])
        self.assertEqual(default.backend, 'software')
        pl = parser().parse_args(['serve', '--models', 'models', '--backend', 'pl',
                                 '--uio', '/dev/uio2', '--udmabuf', '/dev/udmabuf0'])
        self.assertEqual(pl.uio, Path('/dev/uio2'))
        self.assertEqual(pl.udmabuf, Path('/dev/udmabuf0'))

    def test_dma_alignment_cache_commands_and_live_buffer_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in [('phys_addr', '0x10000000'), ('size', '4096'),
                                ('sync_for_device', ''), ('sync_for_cpu', '')]:
                (root/name).write_text(value)
            device = root/'dma'; device.write_bytes(bytes(4096))
            pool = UdmaAllocator(device, root)
            a = pool(shape=(3,), dtype=np.int32)
            b = pool(shape=(3,), dtype=np.int32)
            self.assertEqual((a.physical_address, b.physical_address), (0x10000000, 0x10000040))
            b[:] = [3, 125, -3]
            b.flush()
            b.invalidate()
            self.assertEqual((root/'sync_for_device').read_text(), '0x0000004000000041\n')
            self.assertEqual((root/'sync_for_cpu').read_text(), '0x0000004000000041\n')
            self.assertEqual(np.array(b).tolist(), [3, 125, -3])
            self.assertEqual(device.read_bytes()[64:76], struct.pack('<3i', 3, 125, -3))
            with self.assertRaises(RuntimeError): pool.close()
            a.freebuffer(); b.freebuffer()
            with self.assertRaises(RuntimeError): b.flush()
            c = pool(shape=(3,), dtype=np.int32)
            self.assertEqual(c.physical_address, 0x10000000)
            c.freebuffer(); pool.close()

    def test_uio_verifies_mapping_and_bounds_word_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            info = root/'map0'; info.mkdir()
            for name, value in [('addr', '0x40000000'), ('size', '0x1000'), ('offset', '0')]:
                (info/name).write_text(value)
            device = root/'uio'; device.write_bytes(bytes(4096))
            with self.assertRaises(ValueError):
                UioRegisters(device, info, expected_address=0x43000000)
            regs = UioRegisters(device, info, expected_address=0x40000000)
            regs.write(0x18, 0x12345678)
            self.assertEqual(regs.read(0x18), 0x12345678)
            self.assertEqual(device.read_bytes()[0x18:0x1c], b'\x78\x56\x34\x12')
            for offset in [-4, 1, 4096]:
                with self.assertRaises(ValueError): regs.read(offset)
            regs.close()


if __name__ == '__main__': unittest.main()

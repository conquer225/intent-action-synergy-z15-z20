"""Explicit Linux UIO / u-dma-buf adapters. No /dev/mem fallback."""
import mmap
import os
from pathlib import Path
import struct
import threading
import numpy as np


def _number(path):
    return int(Path(path).read_text().strip(), 0)


def _open_exclusive(path):
    fd = os.open(path, os.O_RDWR)
    try:
        if os.name == 'posix':
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


class UioRegisters:
    def __init__(self, device, map_info, *, expected_address):
        info = Path(map_info)
        self.size = _number(info/'size')
        if (_number(info/'addr') != expected_address or _number(info/'offset') != 0
                or self.size < 0x70 or self.size > 0x10000):
            raise ValueError('UIO map does not match the generated NPU register aperture')
        self.fd = _open_exclusive(device)
        try:
            self.mapping = mmap.mmap(self.fd, self.size, access=mmap.ACCESS_WRITE)
        except BaseException:
            os.close(self.fd)
            raise

    def _offset(self, offset):
        if type(offset) is not int or offset < 0 or offset % 4 or offset+4 > self.size:
            raise ValueError('MMIO requires an aligned word inside the mapped aperture')

    def read(self, offset):
        self._offset(offset)
        return struct.unpack_from('<I', self.mapping, offset)[0]

    def write(self, offset, value):
        self._offset(offset)
        if type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError('MMIO value outside uint32')
        struct.pack_into('<I', self.mapping, offset, value)

    def close(self):
        self.mapping.close()
        os.close(self.fd)


class _DmaBuffer:
    def __init__(self, pool, offset, count, dtype, reserved):
        self.pool, self.offset, self.count, self.dtype = pool, offset, count, dtype
        self.nbytes, self.reserved = count*dtype.itemsize, reserved
        self.physical_address = pool.physical_address+offset
        self.freed = False

    def _view(self):
        if self.freed or self.pool.closed:
            raise RuntimeError('DMA allocation has been released')
        return np.ndarray((self.count,), dtype=self.dtype, buffer=self.pool.mapping,
                          offset=self.offset+getattr(self.pool, 'view_offset', 0))

    def __len__(self): return self.count

    def __getitem__(self, key):
        with self.pool.lock:
            return np.array(self._view()[key], copy=True)

    def __setitem__(self, key, value):
        with self.pool.lock:
            self._view()[key] = value

    def __array__(self, dtype=None, copy=None):
        if copy is False:
            raise ValueError('DMA views cannot escape allocation ownership; request a copy')
        with self.pool.lock:
            return np.array(self._view(), dtype=dtype, copy=True)

    def flush(self): self.pool._sync(self, 'sync_for_device')
    def invalidate(self): self.pool._sync(self, 'sync_for_cpu')

    def freebuffer(self):
        with self.pool.lock:
            self.freed = True


class UdmaAllocator:
    """Single-owner u-dma-buf pool, 64-byte aligned disjoint allocations.

    Kernel driver owns allocation. Cache sync encodes offset/length/direction
    in one sysfs write, per ikwzm/u-dma-buf manual (bidirectional direction=0).
    close refuses live allocations, including HardwareNPU timeout retention.
    """
    def __init__(self, device, sysfs):
        self.sysfs = Path(sysfs)
        self.physical_address, self.size = _number(self.sysfs/'phys_addr'), _number(self.sysfs/'size')
        if (self.physical_address <= 0 or self.physical_address % 64 or self.size < 64
                or self.physical_address+self.size > 0x40000000):
            raise ValueError('u-dma-buf must lie in aligned Z20 low 1 GiB DDR')
        for name in ['sync_for_device', 'sync_for_cpu']:
            if not (self.sysfs/name).is_file():
                raise ValueError('u-dma-buf manual cache synchronization interface missing')
        self.lock, self.buffers, self.offset, self.closed = threading.RLock(), [], 0, False
        self.fd = _open_exclusive(device)
        try:
            self.mapping = mmap.mmap(self.fd, self.size, access=mmap.ACCESS_WRITE)
        except BaseException:
            os.close(self.fd)
            raise

    def __call__(self, *, shape, dtype):
        dtype = np.dtype(dtype)
        if (len(shape) != 1 or type(shape[0]) is not int or shape[0] <= 0
                or dtype not in (np.dtype('int8'), np.dtype('int32'))):
            raise ValueError('expected a one-dimensional int8/int32 DMA allocation')
        reserved = (shape[0]*dtype.itemsize+63)//64*64
        with self.lock:
            if self.closed:
                raise RuntimeError('DMA pool closed')
            if all(b.freed for b in self.buffers):
                self.offset, self.buffers = 0, []
            if self.offset+reserved > self.size:
                raise MemoryError('DMA pool exhausted; live allocations cannot be reused')
            b = _DmaBuffer(self, self.offset, shape[0], dtype, reserved)
            self.buffers.append(b)
            self.offset += reserved
            b[:] = 0
            return b

    def _sync(self, buffer, name):
        with self.lock:
            buffer._view()
            command = (buffer.offset << 32) | buffer.reserved | 1
            payload = f'0x{command:016x}\n'.encode()
            fd = os.open(self.sysfs/name, os.O_WRONLY)
            try:
                if os.write(fd, payload) != len(payload):
                    raise OSError('incomplete DMA cache synchronization request')
            finally:
                os.close(fd)

    def close(self):
        with self.lock:
            if any(not b.freed for b in self.buffers):
                raise RuntimeError('DMA buffers remain owned; verify accelerator idle/reset first')
            if not self.closed:
                self.mapping.close()
                os.close(self.fd)
                self.closed = True


class UioDmaAllocator(UdmaAllocator):
    """Uncached UIO RAM reserved with no-map before Linux boots.

    This pool is separate from the register UIO device so each has one owner.
    It cannot allocate ordinary Linux RAM. The reservation's big-endian reg
    must exactly match the UIO physical aperture. Linux's UIO physical mapper
    uses pgprot_noncached; no u-dma-buf cache-sync operation applies here.
    """
    def __init__(self, device, map_info, reservation):
        info, reservation = Path(map_info), Path(reservation)
        raw = (reservation/'reg').read_bytes()
        self.physical_address, self.size = _number(info/'addr'), _number(info/'size')
        if (len(raw) != 8 or struct.unpack('>II', raw) != (self.physical_address, self.size)
                or not (reservation/'no-map').is_file() or _number(info/'offset') != 0
                or self.physical_address <= 0 or self.physical_address % 4096
                or self.size < 4096 or self.size % 4096
                or self.physical_address+self.size > 0x40000000):
            raise ValueError('UIO RAM must match an aligned boot-time no-map DDR reservation')
        if not info.name.startswith('map') or not info.name[3:].isdigit():
            raise ValueError('expected UIO map index')
        index = int(info.name[3:])
        if not 0 <= index < 16:
            raise ValueError('UIO map index outside supported range')
        self.lock, self.buffers, self.offset, self.closed = threading.RLock(), [], 0, False
        self.fd = _open_exclusive(device)
        try:
            selected = index*mmap.PAGESIZE
            aligned = selected//mmap.ALLOCATIONGRANULARITY*mmap.ALLOCATIONGRANULARITY
            self.view_offset = selected-aligned
            self.mapping = mmap.mmap(self.fd, self.size+self.view_offset,
                                     access=mmap.ACCESS_WRITE, offset=aligned)
        except BaseException:
            os.close(self.fd)
            raise

    def _sync(self, buffer, name):
        with self.lock:
            buffer._view()

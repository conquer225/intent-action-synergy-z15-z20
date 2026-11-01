"""Private prepared YUV blocks; exactly two bounded RAM slots, no DMA or audio."""
import ctypes as C
import json
from pathlib import Path
import queue
import re
import struct
import threading
import zlib
from itertools import cycle

import numpy as np

FRAME_BYTES = 1280 * 720 * 3 // 2
BLOCK_FRAMES = 16
MAX_STORE = 4 * 1024 ** 3
HEADER = struct.Struct('<4sIII')  # magic, encoding, payload bytes, CRC32


class LZ4:
    def __init__(self, path='/usr/lib/arm-linux-gnueabihf/liblz4.so.1', frame_bytes=FRAME_BYTES):
        self.lib = C.CDLL(path)
        self.lib.LZ4_compressBound.argtypes = [C.c_int]
        self.lib.LZ4_compressBound.restype = C.c_int
        self.lib.LZ4_compress_default.argtypes = [C.c_void_p, C.c_void_p, C.c_int, C.c_int]
        self.lib.LZ4_compress_default.restype = C.c_int
        self.lib.LZ4_decompress_safe.argtypes = [C.c_void_p, C.c_void_p, C.c_int, C.c_int]
        self.lib.LZ4_decompress_safe.restype = C.c_int
        self.frame_bytes=frame_bytes
        self.bound = self.lib.LZ4_compressBound(frame_bytes)
        self.output = C.create_string_buffer(self.bound)

    def compress(self, frame):
        n = self.lib.LZ4_compress_default(frame.ctypes.data, self.output,
                                         self.frame_bytes, self.bound)
        if n <= 0:
            raise ValueError('LZ4 compression failed')
        return self.output.raw[:n]

    def decompress(self, payload, frame):
        n = self.lib.LZ4_decompress_safe(payload, frame.ctypes.data, len(payload), frame.size)
        if n != frame.size:
            raise ValueError('Invalid LZ4 block size')


def write_frame(handle, frame, codec, previous=None):
    compressed = codec.compress(frame if previous is None else np.bitwise_xor(frame, previous))
    encoding = (1 if previous is None else 2) if len(compressed) < frame.size else 0
    payload = compressed if encoding else frame.tobytes()
    handle.write(HEADER.pack(b'GLY1', encoding, len(payload), zlib.crc32(payload) & 0xffffffff))
    handle.write(payload)
    return HEADER.size + len(payload)


def read_frame(handle, frame, codec, previous=None):
    header = handle.read(HEADER.size)
    if len(header) != HEADER.size:
        raise ValueError('Truncated frame header')
    magic, encoding, length, crc = HEADER.unpack(header)
    if magic != b'GLY1' or encoding not in (0, 1, 2) or not 1 <= length <= frame.size:
        raise ValueError('Invalid cache frame header')
    if encoding == 2 and previous is None:
        raise ValueError('Delta frame has no block-local reference')
    if encoding == 0 and length != frame.size:
        raise ValueError('Invalid raw frame size')
    payload = handle.read(length)
    if len(payload) != length or zlib.crc32(payload) & 0xffffffff != crc:
        raise ValueError('Cache payload truncated or corrupt')
    if encoding:
        codec.decompress(payload, frame)
        if encoding == 2:np.bitwise_xor(frame, previous, out=frame)
    else:
        frame[:] = np.frombuffer(payload, dtype=np.uint8)


def manifest(root):
    root = Path(root).resolve()
    path = root / 'manifest.json'
    if path.stat().st_size > 1024 ** 2:
        raise ValueError('Cache manifest too large')
    data = json.loads(path.read_text())
    if data.get('format') not in ('gl-yuv420-lz4-v1','gl-bgr24-lz4-v1','gl-bgr24-xor-lz4-v1') or data.get('fps') not in (10,20):
        raise ValueError('Unsupported cache format/rate')
    dimensions=(data.get('width'),data.get('height'))
    if dimensions not in ((1280,720),(640,360),(384,216),(288,512)) or (
            dimensions!=(1280,720) and data['format']!='gl-bgr24-lz4-v1'):
        raise ValueError('Unsupported frame dimensions')
    total = size = 0
    frame_bytes=FRAME_BYTES if data['format']=='gl-yuv420-lz4-v1' else data['width']*data['height']*3
    data['frame_bytes']=frame_bytes
    chunks = data.get('chunks')
    if not isinstance(chunks, list) or not 1 <= len(chunks) <= 4500:
        raise ValueError('Invalid cache chunk count')
    for i, chunk in enumerate(chunks):
        name = chunk.get('file', '')
        if name != 'chunk_%06d.bin' % i or not re.fullmatch(r'chunk_\d{6}\.bin', name):
            raise ValueError('Cache chunk path/order mismatch')
        n = chunk.get('frames')
        if type(n) is not int or not 1 <= n <= BLOCK_FRAMES:
            raise ValueError('Cache chunk frame count exceeds bound')
        target = root / name
        if target.is_symlink() or target.stat().st_size != chunk.get('bytes'):
            raise ValueError('Cache chunk file size mismatch')
        if not n * (HEADER.size + 1) <= chunk['bytes'] <= n * (HEADER.size + frame_bytes):
            raise ValueError('Cache chunk size exceeds bound')
        total += n
        size += chunk['bytes']
    if total != data.get('frames') or size > MAX_STORE:
        raise ValueError('Cache total frame/storage limit mismatch')
    return data


class BoundedChunks:
    """Producer owns a free slot until publishing; consumer releases after use."""
    def __init__(self, root, codec=None, loop=False):
        self.root = Path(root)
        self.meta = manifest(root)
        self.codec = codec or LZ4(frame_bytes=self.meta['frame_bytes'])
        self.slots = [np.empty((BLOCK_FRAMES, self.meta['frame_bytes']), dtype=np.uint8) for _ in range(2)]
        self.free = queue.Queue(maxsize=2)
        self.ready = queue.Queue(maxsize=2)
        for index in range(2):
            self.free.put(index)
        self.cancel = threading.Event()
        self.error = None
        self.complete = False
        self.loop = loop
        self.thread = threading.Thread(target=self._run, name='video-block-reader', daemon=True)
        self.thread.start()

    @property
    def allocated_bytes(self):
        return sum(slot.nbytes for slot in self.slots)

    def _run(self):
        try:
            chunks=cycle(self.meta['chunks']) if self.loop else self.meta['chunks']
            for chunk in chunks:
                while not self.cancel.is_set():
                    try:
                        slot = self.free.get(timeout=.1)
                        break
                    except queue.Empty:
                        continue
                else:
                    return
                with (self.root / chunk['file']).open('rb') as handle:
                    previous=None
                    for frame in self.slots[slot][:chunk['frames']]:
                        if self.cancel.is_set():
                            return
                        read_frame(handle, frame, self.codec, previous)
                        if self.meta['format']=='gl-bgr24-xor-lz4-v1':previous=frame
                    if handle.read(1):
                        raise ValueError('Unexpected trailing cache bytes')
                self.ready.put((slot, chunk['frames']))
            self.complete = True
        except (OSError, ValueError) as error:
            self.error = str(error)

    def acquire(self, timeout=.2):
        if self.ready.empty():
            if self.error:raise ValueError(self.error)
            if self.complete:return None
        try:
            return self.ready.get(timeout=timeout)
        except queue.Empty:
            if self.error:
                raise ValueError(self.error)
            if self.complete:
                return None
            raise TimeoutError('Prepared cache is buffering')

    def release(self, slot):
        self.free.put_nowait(slot)

    def close(self):
        self.cancel.set()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError('Cache reader did not stop')

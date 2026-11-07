"""Injected AXI memory-master drivers with explicit command/buffer ownership."""
import threading
import time
import numpy as np

from .eeg import MAGIC
from .mapping import MAP_MAGIC, MAX_POINTS, MAX_TRAJECTORY


class MemoryKernel:
    def __init__(self, registers, allocate, layout, *, timeout=2., now=time.monotonic, sleep=time.sleep):
        self.registers, self.allocate, self.layout = registers, allocate, dict(layout)
        self.timeout, self.now, self.sleep = timeout, now, sleep
        self.buffers, self.poisoned, self.last_timing = {}, False, {}
        self.lock = threading.RLock()

    def _allocate(self):
        ranges = []
        try:
            for name, (offset, size) in self.layout.items():
                buffer = self.allocate(shape=(size,), dtype=np.int32)
                self.buffers[name] = buffer
                start, end = int(buffer.physical_address), int(buffer.physical_address)+buffer.nbytes
                if start <= 0 or start % 8 or end > 2**32 or any(start < b and end > a for a, b in ranges):
                    raise ValueError('accelerator DMA ranges must be aligned, disjoint and inside 32-bit DDR')
                ranges.append((start, end))
                buffer[:] = 0
                buffer.flush()
        except BaseException:
            for buffer in self.buffers.values():buffer.freebuffer()
            self.buffers.clear()
            raise

    def invoke(self, inputs, *, outputs, scalars=None):
        prepared = {}
        for name, values in inputs.items():
            if name not in self.layout:
                raise ValueError('unknown input buffer')
            values = np.asarray(values)
            if values.dtype != np.int32 or values.ndim != 1 or len(values) > self.layout[name][1]:
                raise ValueError('input must fit the int32 command buffer')
            prepared[name] = values
        if any(name not in self.layout for name in outputs):
            raise ValueError('unknown output buffer')
        with self.lock:
            if self.poisoned:raise RuntimeError('command ownership requires a verified hardware reset')
            if not self.registers.read(0) & 4:raise RuntimeError('accelerator is not idle')
            started = self.now()
            if not self.buffers:self._allocate()
            for name, values in prepared.items():
                self.buffers[name][:len(values)] = values
                self.buffers[name].flush()
            for name, (offset, _) in self.layout.items():
                address = int(self.buffers[name].physical_address)
                self.registers.write(offset, address & 0xffffffff)
                self.registers.write(offset+4, address >> 32)
            for offset, value in (scalars or {}).items():self.registers.write(offset, int(value))
            launched = self.now()
            try:
                self.registers.write(0, 1)
                while not self.registers.read(0) & 2:
                    if self.now()-launched > self.timeout:
                        raise TimeoutError('accelerator command timeout')
                    self.sleep(.0001)
            except BaseException:
                self.poisoned = True
                raise
            result = {}
            for name in outputs:
                self.buffers[name].invalidate()
                result[name] = np.array(self.buffers[name], dtype=np.int32, copy=True)
            self.last_timing = dict(total_seconds=self.now()-started, command_seconds=self.now()-launched,
                scope='host_wall_time_including_MMIO_poll_cache_and_result_copy')
            return result

    def close(self, *, reset_verified=False):
        with self.lock:
            if self.buffers and not reset_verified and (self.poisoned or not self.registers.read(0) & 4):
                raise RuntimeError('hardware still owns DMA buffers')
            for buffer in self.buffers.values():buffer.freebuffer()
            self.buffers.clear();self.poisoned = False


class EEGHardware:
    name = 'PL_filterbank_CSP_SVM'
    def __init__(self, model, registers, allocate, **options):
        self.model, self.needs_reset = model, True
        self.kernel = MemoryKernel(registers, allocate,
            dict(samples=(0x10, 512), params=(0x20, 94), result=(0x30, 16)), **options)

    def reset(self):self.needs_reset = True

    def feed(self, samples):
        values = np.asarray(samples)
        if (values.ndim != 2 or values.shape[1] != 8 or values.dtype != np.int32
                or np.min(values, initial=0) < -8388608 or np.max(values, initial=0) > 8388607):
            raise ValueError('expected signed-24-bit Q8 sample rows')
        results = []
        stride = min(50, self.model.hop)
        for start in range(0, len(values), stride):
            chunk = np.ascontiguousarray(values[start:start+stride])
            output = self.kernel.invoke(dict(samples=chunk.ravel(), params=self.model.parameter_words()),
                outputs=('result',), scalars={0x40: len(chunk), 0x48: int(self.needs_reset)})['result']
            self.needs_reset = False
            if int(output[0]) != MAGIC or output[1] & 8:
                raise ValueError('EEG kernel rejected the model/sample contract')
            if output[1] & 1:
                score = (int(output[6]) << 32) | (int(output[5]) & 0xffffffff)
                valid = bool(output[1] & 2)
                results.append(dict(valid=valid, label=('right' if output[4] else 'left') if valid else None,
                    class_id=int(output[4]) if valid else None, score_q24=score,
                    features=output[8:14].tolist(), sample_count=int(output[2]) & 0xffffffff,
                    window_count=int(output[3]) & 0xffffffff, clipped=int(output[7]) & 0xffffffff,
                    model_sha256=self.model.identity, backend=self.name, control_enabled=False,
                    timing=dict(self.kernel.last_timing)))
        return results

    def close(self, **options):self.kernel.close(**options)


class MapHardware:
    name = 'PL_pointcloud_map_renderer'
    def __init__(self, registers, allocate, *, width=640, height=480, **options):
        if not 1 <= width <= 1280 or not 1 <= height <= 720:raise ValueError('map dimensions')
        self.width, self.height = width, height
        self.kernel = MemoryKernel(registers, allocate, dict(
            vertices=(0x10, (MAX_POINTS+MAX_TRAJECTORY)*4), params=(0x20, 32),
            frame=(0x30, width*height), depth=(0x40, width*height), stats=(0x50, 16)), **options)

    def render(self, scene):
        if (scene.width, scene.height) != (self.width, self.height):raise ValueError('map frame size differs from allocation')
        output = self.kernel.invoke(dict(vertices=scene.vertex_words(), params=scene.parameter_words()),
                                    outputs=('frame', 'stats'))
        stats = output['stats']
        if stats[0] != MAP_MAGIC or stats[1]:raise ValueError('map kernel rejected the scene contract')
        words = output['frame']
        rgb = np.stack(((words >> 16) & 255, (words >> 8) & 255, words & 255), axis=-1).astype(np.uint8)
        return rgb.reshape(self.height, self.width, 3), dict(visible_points=int(stats[2]),
            clipped_points=int(stats[3]), trajectory_segments=int(stats[4]),
            backend=self.name, timing=dict(self.kernel.last_timing), **scene.metadata)

    def close(self, **options):self.kernel.close(**options)

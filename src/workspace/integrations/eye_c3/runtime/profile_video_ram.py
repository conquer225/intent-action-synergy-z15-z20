"""Profile the pinned prepared-video path in ordinary RAM, without DMA or PL."""
import argparse
from contextlib import contextmanager
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np


DISPLAY = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')
SESSION = 'play-93498f59'
VIDEO = 'afbb05f8cef54ef9a7ddadbf2613b0e6'
PINS = {
    'system_hdmi.py': '4cc9d171f43cf905a846bd1e0a1382f36b7826df3579ade1a0d4517f1823b8b9',
    'chunk_cache.py': 'c1f881fa788972b38ef46f1332875878996b8b72124266224d2f0001bb8c3a3e',
    'frame_fitter.so': '68085bd0b802550dda2e6610270e8ee1beb79d914a3e78637f2db326a6688021',
    'menu-shells-portrait-live.npz': '77afb60519d68a3f13e91f8e2238edfde1ae9933a68b5035966aa3ea4481cbcf',
}


class Timings:
    def __init__(self, wall=time.monotonic, cpu=time.thread_time):
        self.wall = wall
        self.cpu = cpu
        self.rows = {}

    @contextmanager
    def measure(self, name):
        wall, cpu = self.wall(), self.cpu()
        try:
            yield
        finally:
            self.rows.setdefault(name, []).append(
                ((self.wall() - wall) * 1000, (self.cpu() - cpu) * 1000))

    def summary(self):
        return {name: dict(calls=len(rows), wall_median_ms=float(np.median(wall)),
            wall_p95_ms=float(np.percentile(wall, 95)), wall_max_ms=max(wall),
            thread_cpu_total_ms=sum(cpu), thread_cpu_median_ms=float(np.median(cpu)))
            for name, rows in self.rows.items()
            for wall, cpu in [tuple(zip(*rows))]}


class RamBuffer(np.ndarray):
    def flush(self):
        # Plain NumPy storage has no DMA cache coherency operation to perform.
        pass


def verify_pins():
    hashes = {name: hashlib.sha256((DISPLAY / name).read_bytes()).hexdigest()
              for name in PINS}
    if hashes != PINS:
        raise ValueError('Active software differs from the audited display payload')
    return hashes


def profile(frames):
    hashes = verify_pins()
    state = json.loads((DISPLAY / (SESSION + '.json')).read_text())
    cache = DISPLAY / 'assets' / VIDEO / 'cache'
    video = next(row for row in state['playlist'] if row['id'] == VIDEO)
    if Path(video['cache']) != cache or state.get('user_controlled') is not True:
        raise ValueError('Unexpected prepared-video scope')
    sys.path.insert(0, str(DISPLAY))
    from chunk_cache import BoundedChunks, LZ4
    from system_hdmi import UnifiedDisplay

    timings = Timings()
    library = C.CDLL(str(DISPLAY / 'frame_fitter.so'))
    library.fit_bgr.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_void_p,
                               C.c_int, C.c_int, C.c_int]
    library.fit_bgr.restype = C.c_int

    def fit(*args):
        with timings.measure('fit_bgr'):
            return library.fit_bgr(*args)

    with timings.measure('menu_cache_load'):
        display = UnifiedDisplay(state['eye_root'], fit, live=True, dimensions=(288, 512),
                                 shell_cache=DISPLAY / 'menu-shells-portrait-live.npz')
    display.controller._enter('video', time.monotonic())
    with timings.measure('labels_first'):
        display.refresh_labels({}, {}, 'pinned clip')
    for _ in range(40):
        with timings.measure('labels_unchanged'):
            if display.refresh_labels({}, {}, 'pinned clip'):
                raise ValueError('Unchanged labels rebuilt')
    for index in range(20):
        with timings.measure('labels_changed_synthetic'):
            changed = display.refresh_labels({'emotion': {'valid': True,
                'label': 'boring' if index % 2 else 'funny'}}, {}, 'pinned clip')
            if not changed:
                raise ValueError('Changed labels were not rendered')

    class ProfiledCodec(LZ4):
        def decompress(self, payload, frame):
            with timings.measure('lz4_decompress_worker'):
                super().decompress(payload, frame)

    buffers = [np.zeros((720, 1280, 3), dtype=np.uint8).view(RamBuffer) for _ in range(3)]
    checked_pixels = 0
    layout_or_feedback_updates = 0
    codec = ProfiledCodec(frame_bytes=288 * 512 * 3)
    start = time.monotonic()
    process_cpu = time.process_time()
    source = None
    try:
        with timings.measure('cache_setup'):
            source = BoundedChunks(cache, codec=codec, loop=True)
        if (source.meta['width'], source.meta['height'], source.meta['fps']) != (288, 512, 20):
            raise ValueError('Unexpected frame dimensions or rate')
        produced = 0
        deadline = time.monotonic()
        while produced < frames:
            with timings.measure('block_acquire_first' if produced == 0 else 'block_acquire'):
                slot, count = source.acquire(timeout=2)
            for local_index in range(min(count, frames - produced)):
                frame = source.slots[slot][local_index]
                target = produced % 3
                with timings.measure('compose_ordinary_ram'):
                    layout_or_feedback_updates += bool(display.compose(buffers[target], target, frame))
                if produced in (0, 1, frames - 2, frames - 1):
                    x, y, width, height = display.roi
                    pixels = frame.reshape((512, 288, 3))
                    expected = pixels[(np.arange(height) * 512 // height)[:, None],
                                      (np.arange(width) * 288 // width)[None, :]]
                    if not np.array_equal(buffers[target][y:y+height, x:x+width], expected):
                        raise ValueError('Fitted ROI differs from independent pixel reference')
                    checked_pixels += 1
                produced += 1
                deadline += .05
                delay = deadline - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            source.release(slot)
    finally:
        if source is not None:
            source.close()
    if verify_pins() != hashes:
        raise ValueError('Pinned files changed during the diagnostic')
    return dict(scope='prepared_cache_and_composition_in_ordinary_RAM', frames=produced,
        elapsed_s=time.monotonic()-start, process_cpu_s=time.process_time()-process_cpu,
        timings=timings.summary(), exact_pixel_checks=checked_pixels,
        compose_layout_or_feedback_updates=layout_or_feedback_updates, hashes=hashes,
        cache_crc_checked=True, synthetic_label_changes=20,
        cache_flush_measured=False, display_submit_measured=False, screen_fps_measured=False,
        pl_loaded=False, audio_output=False, physical_control=False,
        note='Nested timings overlap; worker and main-thread CPU are separate. '
             'The pacing rate is not screen FPS. No MP4 decoder, CMA, DMA or live labels are used.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=int, default=320)
    args = parser.parse_args()
    if not 80 <= args.frames <= 640:
        raise ValueError('Finite profile frame limit')
    print(json.dumps(profile(args.frames), indent=2), flush=True)


if __name__ == '__main__':
    main()

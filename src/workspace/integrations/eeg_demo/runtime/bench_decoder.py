"""Direct BGR output software check. Does not import PYNQ or access MMIO."""
import ctypes as C
import json
from pathlib import Path
import resource
import time

import numpy as np


def load_decoder(path):
    library = C.CDLL(str(path))
    library.video_open.argtypes = [C.c_char_p, C.c_int]
    library.video_open.restype = C.c_void_p
    library.video_close.argtypes = [C.c_void_p]
    library.video_close.restype = None
    library.video_read_to.argtypes = [C.c_void_p, C.c_void_p, C.c_int, C.c_int, C.c_int]
    library.video_read_to.restype = C.c_int
    library.video_rewind.argtypes = [C.c_void_p]
    library.video_rewind.restype = C.c_int
    library.video_fps.argtypes = [C.c_void_p]
    library.video_fps.restype = C.c_double
    return library


def run(library, path, threads):
    output = np.empty((720, 1280, 3), dtype=np.uint8)
    reader = library.video_open(str(path).encode(), threads)
    if not reader:
        raise RuntimeError("Cannot open converted file")
    frames = checksum = 0
    samples = []
    start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        fps = library.video_fps(reader)
        while True:
            before = time.perf_counter()
            result = library.video_read_to(reader, output.ctypes.data, 1280, 720, 1280 * 3)
            if result == 0:
                break
            if result != 1:
                raise RuntimeError("Decoder returned error %d" % result)
            samples.append((time.perf_counter() - before) * 1000)
            frames += 1
            checksum += int(output[0, 0, 0])
        if library.video_rewind(reader) < 0:
            raise RuntimeError("Rewind failed")
        if library.video_read_to(reader, output.ctypes.data, 1280, 720, 1280 * 3) != 1:
            raise RuntimeError("First frame after rewind failed")
    finally:
        library.video_close(reader)
    elapsed = time.perf_counter() - start
    return {"path": str(path), "threads": threads, "frames": frames,
        "source_fps": fps, "checksum": checksum, "wall_s": elapsed,
        "decoded_fps": frames / elapsed,
        "decode_p95_ms": float(np.percentile(samples, 95)),
        "process_cpu_percent": (time.process_time() - cpu_start) / elapsed * 100,
        "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "output": "1280x720 BGR memory, not HDMI"}


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    library = load_decoder(root / "frame_decoder.so")
    results = [run(library, root / ("video_%dx%d.mp4" % size), threads)
               for size in ((1280, 720), (640, 360)) for threads in (1, 2)]
    for index in (0, 2):
        if results[index]["frames"] != results[index + 1]["frames"] or \
           results[index]["checksum"] != results[index + 1]["checksum"]:
            raise RuntimeError("Thread variants differ in frame count or first-pixel checksum")
    (root / "decoder_report.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results), flush=True)

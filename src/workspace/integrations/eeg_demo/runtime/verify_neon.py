"""Software-only colour/timing audit. No PYNQ, speakers, or retained pictures."""
import argparse
import ctypes as C
import json
from pathlib import Path
import time

import numpy as np
from prepare_chunks import decoder


def load_neon(path):
    lib = C.CDLL(str(path))
    lib.neon_bgr_convert.argtypes = [C.c_void_p, C.c_void_p, C.c_int]
    lib.neon_bgr_convert.restype = C.c_int
    return lib


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    base = Path(__file__).resolve().parent
    lib = decoder(base/'frame_decoder.so')
    neon = load_neon(base/'frame_converter_neon.so')
    reader = lib.video_open(str(args.source).encode(), 2)
    if not reader:raise ValueError('Source unavailable')
    converter = lib.bgr_open()
    if not converter:
        lib.video_close(reader)
        raise ValueError('Reference converter unavailable')
    raw = np.empty(1382400, dtype=np.uint8)
    reference = np.empty((720,1280,3), dtype=np.uint8)
    output = np.empty_like(reference)
    count = maximum = differences = total = 0
    reference_s = neon_s = 0
    start = time.monotonic()
    try:
        while True:
            result = lib.video_read_yuv(reader, raw.ctypes.data, 1280, 720)
            if result == 0:break
            if result != 1 or count >= 100 or time.monotonic()-start > 60:
                raise ValueError('Finite audit bounds exceeded')
            before = time.monotonic()
            if lib.bgr_convert(converter, raw.ctypes.data, reference.ctypes.data, 3840)!=1:
                raise ValueError('Reference conversion failed')
            reference_s += time.monotonic()-before
            before = time.monotonic()
            if neon.neon_bgr_convert(raw.ctypes.data, output.ctypes.data, 3840)!=1:
                raise ValueError('NEON conversion failed')
            neon_s += time.monotonic()-before
            error = np.abs(reference.astype(np.int16)-output.astype(np.int16))
            maximum = max(maximum,int(error.max()))
            differences += int(np.count_nonzero(error))
            total += int(error.sum())
            count += 1
    finally:
        lib.video_close(reader);lib.bgr_close(converter)
    report = {'frames_checked':count,'maximum_colour_code_error':maximum,
        'mean_colour_code_error':total/(count*1280*720*3) if count else None,
        'different_codes':differences,'reference_convert_ms_per_frame':reference_s/count*1000 if count else None,
        'neon_convert_ms_per_frame':neon_s/count*1000 if count else None,
        'within_two_codes':bool(count) and maximum<=2,'audio_output':False,'hdmi_tested':False,
        'formula':'BT.601 limited integer 298/409/516/100/208; nearest duplicated chroma',
        'exact_swscale_match':differences==0 and bool(count)}
    args.output.write_text(json.dumps(report));print(json.dumps(report),flush=True)


if __name__=='__main__':main()

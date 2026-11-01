"""Finite offline cache preparation. Source MP4 is preserved; no PL imports."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import resource
import shutil
import time
from io import BytesIO

import numpy as np
from bench_decoder import load_decoder
from chunk_cache import BLOCK_FRAMES, FRAME_BYTES, MAX_STORE, LZ4, write_frame, read_frame


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def decoder(path):
    lib = load_decoder(path)
    lib.video_read_yuv.argtypes = [C.c_void_p, C.c_void_p, C.c_int, C.c_int]
    lib.video_read_yuv.restype = C.c_int
    lib.bgr_open.restype = C.c_void_p
    lib.bgr_convert.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_int]
    lib.bgr_convert.restype = C.c_int
    lib.bgr_close.argtypes = [C.c_void_p]
    return lib


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--repeat-fixture', type=int, default=1)
    p.add_argument('--pixel-format',choices=('yuv420','bgr24'),default='yuv420')
    args = p.parse_args()
    if not 1 <= args.repeat_fixture <= 40:
        raise ValueError('Fixture repetition bound exceeded')
    args.output.mkdir(mode=0o700, exist_ok=False)
    lib = decoder(Path(__file__).with_name('frame_decoder.so'))
    frame_bytes=FRAME_BYTES if args.pixel_format=='yuv420' else 1280*720*3
    codec = LZ4(frame_bytes=frame_bytes)
    raw = np.empty(frame_bytes, dtype=np.uint8)
    recovered = np.empty_like(raw)
    bgr = np.empty((720, 1280, 3), dtype=np.uint8)
    direct = np.empty_like(bgr)
    original_sha = file_sha(args.source)
    start = time.monotonic()
    chunks, frames, used = [], 0, 0
    source_frames = None
    handle = None
    converter = lib.bgr_open()
    if not converter:
        raise RuntimeError('Cannot create YUV converter')
    try:
        for iteration in range(args.repeat_fixture):
            reader = lib.video_open(str(args.source).encode(), 2)
            reference = lib.video_open(str(args.source).encode(), 2)
            if not reader or not reference:
                if reader:lib.video_close(reader)
                if reference:lib.video_close(reference)
                raise ValueError('Source does not decode')
            cycle_frames = 0
            try:
                if abs(lib.video_fps(reader) - 20) > .05:
                    raise ValueError('Prepare a 20fps video copy before creating cache')
                while True:
                    code = lib.video_read_yuv(reader, raw.ctypes.data, 1280, 720) if args.pixel_format=='yuv420' else \
                        lib.video_read_to(reader, raw.ctypes.data, 1280, 720, 3840)
                    if code == 0:
                        break
                    if code != 1 or frames >= 72000:
                        raise ValueError('Decoder/frame limit failed')
                    if iteration == 0:
                        if args.pixel_format=='yuv420':
                            if lib.bgr_convert(converter, raw.ctypes.data, bgr.ctypes.data, 3840)!=1:
                                raise ValueError('YUV reference conversion failed')
                        else:np.copyto(bgr,raw.reshape((720,1280,3)))
                        if lib.video_read_to(reference, direct.ctypes.data, 1280, 720, 3840) != 1 or not np.array_equal(direct,bgr):
                            raise ValueError('Prepared YUV differs from software BGR reference')
                    if frames % BLOCK_FRAMES == 0:
                        if handle:
                            handle.close()
                        name = 'chunk_%06d.bin' % len(chunks)
                        handle = (args.output / name).open('xb')
                        chunks.append({'file': name, 'frames': 0, 'bytes': 0})
                    if used + frame_bytes + 16 > MAX_STORE or \
                       shutil.disk_usage(args.output).free < frame_bytes + 1024 ** 3:
                        raise ValueError('Prepared cache quota/free-space limit reached; not published')
                    before = handle.tell()
                    encoded = BytesIO()
                    count = write_frame(encoded, raw, codec)
                    encoded.seek(0)
                    read_frame(encoded, recovered, codec)
                    if not np.array_equal(raw, recovered):
                        raise ValueError('Cache compression round-trip differs')
                    handle.write(encoded.getbuffer())
                    if handle.tell()-before!=count:raise ValueError('Cache write count mismatch')
                    chunks[-1]['frames'] += 1
                    chunks[-1]['bytes'] += count
                    used += count
                    frames += 1
                    cycle_frames += 1
                    if time.monotonic() - start > 900:
                        raise TimeoutError('Finite cache preparation exceeded 15 minutes')
            finally:
                lib.video_close(reader)
                lib.video_close(reference)
            if source_frames is None:
                source_frames = cycle_frames
            if not cycle_frames or cycle_frames != source_frames:
                raise ValueError('Fixture/source count mismatch')
        if handle:
            handle.close()
            handle = None
        for chunk in chunks:
            with (args.output / chunk['file']).open('rb') as block:
                for _ in range(chunk['frames']):
                    read_frame(block, recovered, codec)
                if block.read(1):raise ValueError('Cache trailing bytes')
        if file_sha(args.source) != original_sha:
            raise ValueError('Source changed during preparation')
        report = {'format':'gl-'+args.pixel_format+'-lz4-v1','width':1280,'height':720,'fps':20,
            'frames':frames,'chunks':chunks,'stored_bytes':used,'source_sha256':original_sha,
            'source_frames':source_frames,'source_cycles':args.repeat_fixture,
            'repeated_fixture_not_new_long_recording':args.repeat_fixture > 1,
            'all_source_frames_match_bgr_reference':True,'original_preserved':True,
            'audio_output':False,'wall_s':time.monotonic()-start,
            'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}
        part = args.output / 'manifest.part'
        part.write_text(json.dumps(report))
        part.rename(args.output / 'manifest.json')
        print(json.dumps({k:v for k,v in report.items() if k != 'chunks'}),flush=True)
    finally:
        if handle:handle.close()
        lib.bgr_close(converter)


if __name__ == '__main__':main()

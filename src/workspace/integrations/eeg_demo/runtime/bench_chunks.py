"""Read prepared blocks at 20fps without PYNQ; memory usage independent of duration."""
import argparse
import json
from pathlib import Path
import resource
import time

import numpy as np
from chunk_cache import BoundedChunks
from prepare_chunks import decoder


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--unpaced', action='store_true')
    p.add_argument('--output',type=Path)
    args = p.parse_args()
    source = BoundedChunks(args.cache)
    lib = decoder(Path(__file__).with_name('frame_decoder.so'))
    convert = lib.bgr_open()
    if not convert:raise ValueError('YUV converter unavailable')
    output = np.empty((720,1280,3),dtype=np.uint8)
    count = 0
    waits = []
    start = time.monotonic()
    cpu = time.process_time()
    try:
        while True:
            before = time.monotonic()
            block = source.acquire(timeout=10)
            waits.append(time.monotonic()-before)
            if block is None:break
            slot,n = block
            try:
                for frame in source.slots[slot][:n]:
                    if not args.unpaced:
                        time.sleep(max(0,start+count/20-time.monotonic()))
                    if source.meta['format'] in ('gl-bgr24-lz4-v1','gl-bgr24-xor-lz4-v1'):np.copyto(output,frame.reshape((720,1280,3)))
                    elif lib.bgr_convert(convert,frame.ctypes.data,output.ctypes.data,3840)!=1:
                        raise ValueError('YUV conversion failed')
                    count += 1
            finally:source.release(slot)
    finally:
        source.close()
        lib.bgr_close(convert)
    wall=time.monotonic()-start
    report={'frames':count,'wall_s':wall,'fps':count/wall,
        'cpu_percent':(time.process_time()-cpu)/wall*100,
        'bounded_ram_mib':source.allocated_bytes/1024**2,
        'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        'max_block_wait_s':max(waits),'unpaced':args.unpaced,'hdmi_tested':False}
    if args.output:args.output.write_text(json.dumps(report))
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()

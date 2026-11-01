"""Finite short-fixture throughput fallback: 360p detail, 720p HDMI output."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import resource
import shutil
import time

import numpy as np
from chunk_cache import LZ4, BLOCK_FRAMES, MAX_STORE, read_frame, write_frame
from prepare_chunks import decoder, file_sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--compact',action='store_true');args=p.parse_args()
    args.output.mkdir(mode=0o700,exist_ok=False)
    start=time.monotonic();original_sha=file_sha(args.source)
    lib=decoder(Path(__file__).with_name('frame_decoder.so'));reader=lib.video_open(str(args.source).encode(),2)
    if not reader:raise ValueError('Fixture decoder failed')
    frame=np.empty((720,1280,3),dtype=np.uint8)
    stored_width,stored_height=(640,360) if args.compact else (1280,720)
    recovered=np.empty(stored_width*stored_height*3,dtype=np.uint8)
    codec=LZ4(frame_bytes=recovered.size);encoded=[]
    try:
        if abs(lib.video_fps(reader)-20)>.05:raise ValueError('A prepared 20fps fixture is required')
        while True:
            result=lib.video_read_to(reader,frame.ctypes.data,1280,720,3840)
            if result==0:break
            if result!=1 or len(encoded)>=64:raise ValueError('Only short fixtures up to 64 frames are allowed')
            # The lossy spatial step is explicit, ahead of lossless cache compression.
            small=frame[::2,::2].copy()
            preview=small.reshape(-1) if args.compact else np.repeat(np.repeat(small,2,axis=0),2,axis=1).reshape(-1)
            out=BytesIO();write_frame(out,preview,codec);out.seek(0);read_frame(out,recovered,codec)
            if not np.array_equal(preview,recovered):raise ValueError('Preview cache roundtrip differs')
            encoded.append(out.getvalue())
    finally:lib.video_close(reader)
    if not encoded:raise ValueError('Empty fixture')
    chunks=[];used=0;count=len(encoded)*22
    for first in range(0,count,BLOCK_FRAMES):
        path=args.output/('chunk_%06d.bin'%len(chunks));n=min(BLOCK_FRAMES,count-first)
        needed=sum(len(encoded[i%len(encoded)]) for i in range(first,first+n))
        if used+needed>MAX_STORE or shutil.disk_usage(args.output).free<needed+1024**3:
            raise ValueError('Cache quota/free-space reserve exceeded')
        with path.open('xb') as out:
            for i in range(first,first+n):out.write(encoded[i%len(encoded)])
        size=path.stat().st_size;used+=size
        if used>MAX_STORE:raise ValueError('Fixture cache quota exceeded')
        chunks.append(dict(file=path.name,frames=n,bytes=size))
    if file_sha(args.source)!=original_sha:raise ValueError('Source changed')
    data=dict(format='gl-bgr24-lz4-v1',width=stored_width,height=stored_height,fps=20,frames=count,chunks=chunks,
        stored_bytes=used,effective_video_width=640,effective_video_height=360,
        spatial_transform='nearest_360p_detail_upscaled_to_720p; not full-resolution 720p',
        source_sha256=original_sha,source_frames=len(encoded),source_cycles=22,
        repeated_fixture_not_new_long_recording=True,all_preview_frames_match_software_reference=True,
        original_preserved=True,audio_output=False,wall_s=time.monotonic()-start,
        peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    part=args.output/'manifest.part';part.write_text(json.dumps(data));part.rename(args.output/'manifest.json')
    print(json.dumps({k:v for k,v in data.items() if k!='chunks'}),flush=True)


if __name__=='__main__':main()

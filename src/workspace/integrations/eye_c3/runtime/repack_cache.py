"""Prepare block-local deltas or the exact central-display pixels offline."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import resource
import shutil
import time

import numpy as np
from chunk_cache import LZ4, MAX_STORE, manifest, read_frame, write_frame


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fit-central',action='store_true');args=p.parse_args()
    data=manifest(args.input)
    if data['format']!='gl-bgr24-lz4-v1':raise ValueError('Verified BGR input required')
    if args.fit_central and (data['width'],data['height'])!=(640,360):
        raise ValueError('Central fit requires the verified 640x360 input')
    args.output.mkdir(mode=0o700,exist_ok=False)
    source_codec=LZ4(frame_bytes=data['frame_bytes'])
    frame_bytes=384*216*3 if args.fit_central else data['frame_bytes']
    codec=LZ4(frame_bytes=frame_bytes)
    previous=np.empty(frame_bytes,dtype=np.uint8)
    raw=np.empty(data['frame_bytes'],dtype=np.uint8);check=np.empty_like(previous)
    xs=np.arange(384)*640//384;ys=np.arange(216)*360//216
    used=0;chunks=[];start=time.monotonic()
    for chunk in data['chunks']:
        path=args.output/chunk['file'];written=0
        with (args.input/chunk['file']).open('rb') as source,path.open('xb') as dest:
            for index in range(chunk['frames']):
                read_frame(source,raw,source_codec)
                frame=raw.reshape((360,640,3))[ys[:,None],xs[None,:]].reshape(-1) if args.fit_central else raw
                if time.monotonic()-start>900 or shutil.disk_usage(args.output).free<frame_bytes+1024**3:
                    raise ValueError('Finite preparation/storage reserve exceeded')
                reference=previous if index and not args.fit_central else None
                encoded=BytesIO();n=write_frame(encoded,frame,codec,reference)
                if used+n>MAX_STORE:raise ValueError('Cache quota exceeded')
                encoded.seek(0);read_frame(encoded,check,codec,reference)
                if not np.array_equal(check,frame):raise ValueError('Prepared display pixels mismatch')
                dest.write(encoded.getbuffer());np.copyto(previous,frame);used+=n;written+=n
            if source.read(1):raise ValueError('Source has trailing data')
        chunks.append(dict(file=chunk['file'],frames=chunk['frames'],bytes=written))
    data.update(format='gl-bgr24-lz4-v1' if args.fit_central else 'gl-bgr24-xor-lz4-v1',
        chunks=chunks,stored_bytes=used,frame_bytes=frame_bytes,
        lossless_delta_all_frames_verified=not args.fit_central,repack_wall_s=time.monotonic()-start,
        repack_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    if args.fit_central:
        data.update(width=384,height=216,effective_video_width=384,effective_video_height=216,
                    pre_scaled_from_dimensions=[640,360],fitted_all_frames_verified=True)
    part=args.output/'manifest.part';part.write_text(json.dumps(data));part.rename(args.output/'manifest.json')
    print(json.dumps({k:v for k,v in data.items() if k!='chunks'}),flush=True)


if __name__=='__main__':main()

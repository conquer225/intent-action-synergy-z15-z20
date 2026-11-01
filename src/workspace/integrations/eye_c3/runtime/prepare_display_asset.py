"""Direct bilinear fit into a portrait canvas; lossless bounded cache afterwards."""
import ctypes as C
from io import BytesIO
import math
from pathlib import Path
import shutil
import time

import numpy as np
from chunk_cache import LZ4,BLOCK_FRAMES,MAX_STORE,write_frame,read_frame
from upload_server import write_json,file_sha


def fit_geometry(width,height,aspect,rotation):
    if width<=0 or height<=0 or not math.isfinite(aspect) or not .1<=aspect<=10:
        raise ValueError('Invalid source geometry')
    if rotation not in (0,90,180,270):raise ValueError('Unsupported video rotation')
    dw,dh=width*aspect,height
    if rotation in (90,270):dw,dh=dh,dw
    ratio=min(288/dw,512/dh)
    w,h=max(1,min(288,round(dw*ratio))),max(1,min(512,round(dh*ratio)))
    return w,h,(288-w)//2,(512-h)//2


def prepare(source,output):
    source=Path(source);output=Path(output);output.mkdir(mode=0o700,exist_ok=False)
    from bench_decoder import load_decoder
    digest=file_sha(source);base=Path(__file__).resolve().parent;lib=load_decoder(base/'frame_decoder.so')
    for name in ('video_width','video_height','video_rotation'):
        fn=getattr(lib,name);fn.argtypes=[C.c_void_p];fn.restype=C.c_int
    lib.video_aspect.argtypes=[C.c_void_p];lib.video_aspect.restype=C.c_double
    reader=lib.video_open(str(source).encode(),2)
    if not reader:raise ValueError('Video does not decode')
    handle=None;start=time.monotonic();chunks=[];count=decoded=used=0
    canvas=np.zeros((512,288,3),dtype=np.uint8);check=np.empty(canvas.size,dtype=np.uint8)
    codec=LZ4(frame_bytes=canvas.size)
    try:
        rotation=lib.video_rotation(reader);width=lib.video_width(reader);height=lib.video_height(reader)
        w,h,x,y=fit_geometry(width,height,lib.video_aspect(reader),rotation)
        sw,sh=(h,w) if rotation in (90,270) else (w,h)
        pixels=np.empty((sh,sw,3),dtype=np.uint8)
        fps=lib.video_fps(reader)
        if not math.isfinite(fps) or not 10<=fps<=240:raise ValueError('Unsupported source frame rate')
        target=10 if fps<20 else 20
        while True:
            result=lib.video_read_to(reader,pixels.ctypes.data,sw,sh,sw*3)
            if result==0:break
            if result!=1:raise ValueError('Decode failed')
            source_time=decoded/fps;decoded+=1
            if source_time+1e-6<count/target:continue
            if count>=12000 or time.monotonic()-start>900:raise ValueError('Finite preparation limit exceeded')
            oriented=np.rot90(pixels,-rotation//90) if rotation else pixels
            np.copyto(canvas[y:y+h,x:x+w],oriented)
            frame=canvas.reshape(-1);data=BytesIO();n=write_frame(data,frame,codec)
            data.seek(0);read_frame(data,check,codec)
            if not np.array_equal(frame,check):raise ValueError('Cache roundtrip mismatch')
            if used+n>MAX_STORE or shutil.disk_usage(output).free<n+1024**3:raise ValueError('Cache storage quota exceeded')
            if count%BLOCK_FRAMES==0:
                if handle:handle.close()
                name='chunk_%06d.bin'%len(chunks);handle=(output/name).open('xb')
                chunks.append(dict(file=name,frames=0,bytes=0))
            handle.write(data.getbuffer());chunks[-1]['frames']+=1;chunks[-1]['bytes']+=n;count+=1;used+=n
        if not count:raise ValueError('Empty video')
        if file_sha(source)!=digest:raise ValueError('Uploaded original changed')
        handle.close();handle=None
        write_json(output/'manifest.json',dict(format='gl-bgr24-lz4-v1',width=288,height=512,fps=target,
            frames=count,chunks=chunks,stored_bytes=used,source_sha256=digest,original_preserved=True,
            source_dimensions=[width,height],source_rotation=rotation,source_fps=fps,source_frames=decoded,
            fit_rect=[x,y,w,h],spatial_transform='direct FFmpeg bilinear contain; black letterbox; no stretch',
            repeated_fixture_not_new_long_recording=False,audio_output=False,all_cache_frames_verified=True,
            wall_s=time.monotonic()-start))
    finally:
        if handle:handle.close()
        lib.video_close(reader)

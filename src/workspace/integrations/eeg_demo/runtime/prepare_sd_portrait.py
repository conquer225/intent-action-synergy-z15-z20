"""Recover the explicit black-padded SD portrait fixture, not new source detail."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import struct
import subprocess
import time

import numpy as np
from PIL import Image
from chunk_cache import BLOCK_FRAMES,LZ4,write_frame,read_frame
from upload_server import write_json,file_sha


def fit_sd(path):
    with Image.open(path) as image:
        pixels=np.asarray(image.convert('RGB'))
        if image.size!=(640,360):raise ValueError('Unexpected SD fixture size')
        # This crop is specific to the two inspected, black-padded SD assets.
        if pixels[:,:214].max()>35 or pixels[:,426:].max()>35:
            raise ValueError('SD padding is not black; refuse an unverified crop')
        bilinear=getattr(Image,'Resampling',Image).BILINEAR
        return image.crop((218,0,420,360)).resize((288,512),bilinear).convert('RGB')


def jpeg_avi(path,frames,fps):
    """Finite MJPEG intermediate accepted by the existing FFmpeg converter."""
    def chunk(tag,data):return tag+struct.pack('<I',len(data))+data+(b'\0' if len(data)%2 else b'')
    largest=max(map(len,frames));n=len(frames)
    avih=struct.pack('<14I',1000000//fps,largest*fps,0,0x10,n,0,1,largest,288,512,0,0,0,0)
    strh=struct.pack('<4s4sIHH8I4h',b'vids',b'MJPG',0,0,0,0,1,fps,0,n,largest,0xffffffff,0,0,0,288,512)
    strf=struct.pack('<IiiHH4sIiiII',40,288,512,1,24,b'MJPG',288*512*3,0,0,0,0)
    hdrl=chunk(b'LIST',b'hdrl'+chunk(b'avih',avih)+chunk(b'LIST',b'strl'+chunk(b'strh',strh)+chunk(b'strf',strf)))
    movie=bytearray(b'movi');index=bytearray()
    for data in frames:
        index.extend(struct.pack('<4sIII',b'00dc',0x10,len(movie),len(data)))
        movie.extend(chunk(b'00dc',data))
    body=b'AVI '+hdrl+chunk(b'LIST',movie)+chunk(b'idx1',index)
    with path.open('xb') as stream:stream.write(b'RIFF'+struct.pack('<I',len(body))+body)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    start=time.monotonic();args.output.mkdir(mode=0o700,exist_ok=False)
    paths=sorted(args.source.glob('frame_*.jpg'))
    if not 1<=len(paths)<=400:raise ValueError('SD fixture count exceeded')
    hashes={p.name:file_sha(p) for p in paths};cache=args.output/'cache';cache.mkdir()
    codec=LZ4(frame_bytes=288*512*3);check=np.empty(288*512*3,dtype=np.uint8)
    chunks=[];encoded_jpegs=[];handle=None;used=0
    try:
        for i,path in enumerate(paths):
            image=fit_sd(path);bgr=np.asarray(image)[:,:,::-1].copy().reshape(-1)
            jpeg=BytesIO();image.save(jpeg,format='JPEG',quality=94);encoded_jpegs.append(jpeg.getvalue())
            if i%BLOCK_FRAMES==0:
                if handle:handle.close()
                name='chunk_%06d.bin'%len(chunks);handle=(cache/name).open('xb')
                chunks.append(dict(file=name,frames=0,bytes=0))
            data=BytesIO();n=write_frame(data,bgr,codec);data.seek(0);read_frame(data,check,codec)
            if not np.array_equal(check,bgr):raise ValueError('Portrait cache roundtrip differs')
            handle.write(data.getbuffer());chunks[-1]['frames']+=1;chunks[-1]['bytes']+=n;used+=n
        handle.close();handle=None
        avi=args.output/'portrait-source.avi';jpeg_avi(avi,encoded_jpegs,10)
        conversion=subprocess.run([str(Path(__file__).with_name('transcode_video')),str(avi),
            str(args.output/'portrait.mp4'),'288','512','10','60'],capture_output=True,text=True,check=True,timeout=150)
        if {p.name:file_sha(p) for p in paths}!=hashes:raise ValueError('SD originals changed')
        write_json(cache/'manifest.json',dict(format='gl-bgr24-lz4-v1',width=288,height=512,fps=10,
            frames=len(paths),chunks=chunks,stored_bytes=used,source_frames=len(paths),source_cycles=1,
            source_hashes=hashes,original_preserved=True,audio_output=False,
            repeated_fixture_not_new_long_recording=False,
            spatial_transform='verified SD black-padding crop 218:420; bilinear fit; no recovered source detail',
            effective_video_width=202,effective_video_height=360,all_cache_frames_verified=True))
        write_json(args.output/'ready.json',dict(conversion=json.loads(conversion.stdout),
            frames=len(paths),fps=10,wall_s=time.monotonic()-start,download='portrait.mp4'))
    finally:
        if handle:handle.close()


if __name__=='__main__':main()

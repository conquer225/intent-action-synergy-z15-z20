"""Compare private BGR fit libraries in ordinary RAM, never PYNQ or DMA."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import time

import numpy as np


def load(path):
    library=C.CDLL(str(Path(path).resolve()))
    library.fit_bgr.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_void_p,C.c_int,C.c_int,C.c_int]
    library.fit_bgr.restype=C.c_int
    return library


def check(libraries):
    random=np.random.default_rng(101009)
    cases=((288,512,270,480),(640,360,384,216),(360,640,216,384),
           (1280,720,1280,720),(13,7,27,19),(1,1,270,480),(288,512,1,1))
    digest=hashlib.sha256()
    for sw,sh,dw,dh in cases:
        source=random.integers(0,256,(sh,sw,3),dtype=np.uint8)
        expected=source[(np.arange(dh)*sh//dh)[:,None],(np.arange(dw)*sw//dw)[None,:]]
        digest.update(expected.tobytes())
        for library in libraries:
            output=np.full((dh+2,dw*3+32),213,dtype=np.uint8)
            destination=output[1:dh+1]
            if library.fit_bgr(source.ctypes.data,sw,sh,destination.ctypes.data,dw,dh,output.shape[1])!=1:
                raise RuntimeError('Valid reference case refused')
            if not np.array_equal(destination[:,:dw*3].reshape(dh,dw,3),expected):
                raise RuntimeError('Fit pixels differ from the independent reference')
            if not (np.all(destination[:,dw*3:]==213) and np.all(output[0]==213) and np.all(output[-1]==213)):
                raise RuntimeError('Fit overwrote padding or boundary guards')
    for library in libraries:
        source=np.zeros((7,13,3),dtype=np.uint8)
        output=np.full((19,27*3),213,dtype=np.uint8)
        for width,height,stride in ((0,19,81),(1281,19,3843),(27,721,81),(27,19,80)):
            if library.fit_bgr(source.ctypes.data,13,7,output.ctypes.data,width,height,stride)!=0 or not np.all(output==213):
                raise RuntimeError('Invalid dimensions or stride wrote a destination')
        if (library.fit_bgr(None,13,7,output.ctypes.data,27,19,81)!=0 or
                library.fit_bgr(source.ctypes.data,13,7,None,27,19,81)!=0):
            raise RuntimeError('Null pointer accepted')
    return dict(cases=len(cases),exact_pixels_and_padding=True,sha256=digest.hexdigest())


def measure(library,source,output,count):
    wall=[];cpu=[]
    for _ in range(count):
        started=time.perf_counter();cpu_started=time.process_time()
        if library.fit_bgr(source.ctypes.data,288,512,output.ctypes.data,270,480,output.shape[1])!=1:
            raise RuntimeError('Private RAM fit failed')
        cpu.append((time.process_time()-cpu_started)*1000)
        wall.append((time.perf_counter()-started)*1000)
    return dict(frames=count,wall_median_ms=float(np.median(wall)),wall_p95_ms=float(np.percentile(wall,95)),
                wall_max_ms=max(wall),cpu_median_ms=float(np.median(cpu)),cpu_total_seconds=sum(cpu)/1000,
                fitted_sha256=hashlib.sha256(output[:,:810].tobytes()).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--frames',type=int,default=500)
    args=parser.parse_args()
    if not 50<=args.frames<=1000:raise ValueError('Finite benchmark frame limit')
    reference,candidate=load(args.reference),load(args.candidate)
    verification=check((reference,candidate))
    source=np.random.default_rng(7301).integers(0,256,(512,288,3),dtype=np.uint8)
    output=np.zeros((480,3840),dtype=np.uint8)
    rows=[]
    for order in ((('reference',reference),('candidate',candidate)),
                  (('candidate',candidate),('reference',reference))):
        result={}
        for name,library in order:result[name]=measure(library,source,output,args.frames)
        if result['reference']['fitted_sha256']!=result['candidate']['fitted_sha256']:
            raise RuntimeError('Timed fit output changed')
        rows.append(result)
    print(json.dumps(dict(verification=verification,runs=rows,
        scope='normal_RAM_fit_only_no_CMA_flush_no_DMA_no_screen_FPS',
        source_dimensions=[288,512],destination_dimensions=[270,480],audio_output=False,
        physical_output_enabled=False)),flush=True)


if __name__=='__main__':main()

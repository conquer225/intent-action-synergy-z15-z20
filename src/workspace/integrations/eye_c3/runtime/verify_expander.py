"""Exact nearest-neighbour golden check, including padded destination stride."""
import ctypes as C
import json
from pathlib import Path
import time

import numpy as np


def main():
    root=Path(__file__).resolve().parent
    lib=C.CDLL(str(root/'frame_expander.so'))
    lib.expand_bgr_360.argtypes=[C.c_void_p,C.c_void_p,C.c_int]
    lib.expand_bgr_360.restype=C.c_int
    rng=np.random.RandomState(7)
    frames=[np.zeros((360,640,3),dtype=np.uint8),np.full((360,640,3),255,dtype=np.uint8),
            rng.randint(0,256,(360,640,3),dtype=np.uint8)]
    times=[]
    for frame in frames:
        reference=np.repeat(np.repeat(frame,2,axis=0),2,axis=1).reshape(720,3840)
        for stride in (3840,3872):
            output=np.full((720,stride),73,dtype=np.uint8)
            before=time.monotonic()
            if lib.expand_bgr_360(frame.ctypes.data,output.ctypes.data,stride)!=1:
                raise ValueError('Expansion failed')
            times.append((time.monotonic()-before)*1000)
            if not np.array_equal(reference,output[:,:3840]) or not np.all(output[:,3840:]==73):
                raise ValueError('Pixels or stride guard differ from software reference')
    if lib.expand_bgr_360(None,None,0)!=0:raise ValueError('Invalid pointers were accepted')
    report=dict(exact_reference_match=True,cases=6,stride_guards_unchanged=True,
        input_dimensions=[640,360],output_dimensions=[1280,720],
        expansion_ms=times,audio_output=False,hdmi_tested=False)
    (root/'expander_audit.json').write_text(json.dumps(report));print(json.dumps(report),flush=True)


if __name__=='__main__':main()

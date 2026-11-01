"""Run C localization on local images specified by a private JSON manifest.

Manifest: [{"sample":"raw","path":"...png","expected":1,"crop":null}].
crop, when supplied, is [x,y,width,height]. Images never go into the release.
"""
import argparse
import ctypes as C
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'local/face_reference_env'))
import cv2
class Roi(C.Structure):
    _fields_=[(n,C.c_uint16) for n in ('x','y','w','h')]+[('margin',C.c_uint8),('floor',C.c_uint8)]
class Box(C.Structure):
    _fields_=[(n,C.c_uint16) for n in ('x','y','w','h')]+[('valid',C.c_uint8)]
class Loc(C.Structure):
    _fields_=[('face',Box),('left',Roi),('right',Roi)]+[(n,C.c_int) for n in ('valid','faces','eye_count')]

def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    samples=json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    lib=C.CDLL(str(ROOT/'tests/localize.dll'))
    lib.auto_localize.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32,C.POINTER(Loc)]
    args.output.mkdir(parents=True,exist_ok=True)
    records=[]
    for sample in samples:
        label=sample['sample']
        assert label.replace('_','').isalnum()
        im=cv2.imread(sample['path'])
        assert im is not None, 'Missing replay sample: '+label
        if sample.get('crop'):
            x,y,w,h=sample['crop']; im=im[y:y+h,x:x+w].copy()
        loc=Loc(); started=time.perf_counter()
        ok=lib.auto_localize(im.ctypes.data,im.strides[0],im.shape[1],im.shape[0],C.byref(loc))
        record=dict(sample=label,valid=ok,faces=loc.faces,
                    host_ms=round((time.perf_counter()-started)*1000,2))
        assert ok==sample['expected'], (label,ok,sample['expected'])
        annotated=im.copy()
        for key in ('face','left','right'):
            box=getattr(loc,key); record[key]=[box.x,box.y,box.w,box.h]
            if ok:
                assert box.w>0 and box.h>0 and box.x+box.w<=im.shape[1] and box.y+box.h<=im.shape[0]
                cv2.rectangle(annotated,(box.x,box.y),(box.x+box.w,box.y+box.h),
                              (0,255,255) if key=='face' else (0,255,0),2)
        if ok:
            # Destructive eye occlusion must not fall back to guessed face proportions.
            masked=im.copy(); f=loc.face
            y0=f.y+f.h//5; y1=f.y+f.h*3//5
            masked[y0:y1,f.x:f.x+f.w]=128
            other=Loc()
            assert not lib.auto_localize(masked.ctypes.data,masked.strides[0],masked.shape[1],masked.shape[0],C.byref(other)), label
            record['masked_eyes_rejected']=True
        cv2.imwrite(str(args.output/(label+'.png')),annotated)
        records.append(record)
    assert records, 'No replay samples supplied'
    print(json.dumps(records,indent=2))
    (ROOT/'report/replay_results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
if __name__=='__main__':
    run()

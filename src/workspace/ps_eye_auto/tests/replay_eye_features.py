"""Recheck screenshot eye interiors with actual C, excluding colored borders.
Private crops are not shipped. This is not raw camera or gaze ground truth.
"""
import argparse
import ctypes as C
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pc_gaze import GazeEngine
from pc_model import Roi,np,cv2

class Feature(C.Structure):
    _fields_=[('valid',C.c_uint8),('x',C.c_uint16),('y',C.c_uint16),('dark_count',C.c_uint16),
              ('min_gray',C.c_uint8),('max_gray',C.c_uint8),('contrast',C.c_uint8),('confidence',C.c_uint8),
              ('normalized_x',C.c_uint16),('sample_count',C.c_uint16),('selected_count',C.c_uint16),
              ('threshold',C.c_uint8),('reason',C.c_uint8)]

def bind(engine):
    lib=engine.lib
    lib.pc_feature_abi_value.argtypes=[C.c_uint];lib.pc_feature_abi_value.restype=C.c_uint
    expected=[C.sizeof(Feature)]+[getattr(Feature,n).offset for n,_ in Feature._fields_]
    assert [lib.pc_feature_abi_value(i) for i in range(len(expected))]==expected
    lib.eye_analyze_rgb888.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32,C.POINTER(Roi),C.POINTER(Feature)]
    lib.eye_analyze_rgb888.restype=C.c_int
    return lib

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);args=p.parse_args()
    engine=GazeEngine();lib=bind(engine);records=[]
    canvas=np.full((3*180,850,3),240,np.uint8)
    for row,name in enumerate(('near','far','no_glasses')):
        for eye in (0,1):
            path=args.input/f'{name}{eye}.png'
            a=cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_COLOR)
            if a is None:raise RuntimeError('Missing private crop: '+str(path))
            f=Feature();roi=Roi(0,0,a.shape[1],a.shape[0],24,80)
            lib.eye_analyze_rgb888(a.ctypes.data,a.strides[0],a.shape[1],a.shape[0],C.byref(roi),C.byref(f))
            record=dict(sample=path.stem,**{n:getattr(f,n) for n,_ in f._fields_});records.append(record)
            assert f.valid,record
            z=a.copy();cv2.drawMarker(z,(f.x,f.y),(0,240,0),cv2.MARKER_CROSS,9,1)
            x=eye*420;y=row*180+40
            canvas[y:y+110,x:x+190]=cv2.resize(a,(190,110),interpolation=cv2.INTER_NEAREST)
            canvas[y:y+110,x+200:x+390]=cv2.resize(z,(190,110),interpolation=cv2.INTER_NEAREST)
            cv2.putText(canvas,f'{name} eye{eye+1}: C dark core',(x,y-14),0,.48,(0,0,0),1)
    engine.close()
    (args.input/'r3_features.json').write_text(json.dumps(dict(
        source='Screenshot eye interiors, red border excluded; not raw gaze ground truth',results=records),indent=2))
    cv2.imencode('.png',canvas)[1].tofile(args.input/'r3_eye_centers.png')
    print('PASS six screenshot interiors; C-selected dark cores. No live accuracy claim.')
if __name__=='__main__':main()

"""Host adapter. OpenCV handles image I/O/drawing; inference is production C."""
import ctypes as C
import hashlib
import json
import sys
import threading
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
# Existing isolated reference packages on this workstation; portable installs use a venv.
sys.path.insert(0,str(ROOT.parent/'local/face_reference_env'))
import cv2
import numpy as np

class Roi(C.Structure):
    _fields_=[(n,C.c_uint16) for n in ('x','y','w','h')]+[('margin',C.c_uint8),('floor',C.c_uint8)]
class Box(C.Structure):
    _fields_=[(n,C.c_uint16) for n in ('x','y','w','h')]+[('valid',C.c_uint8)]
class Loc(C.Structure):
    _fields_=[('face',Box),('left',Roi),('right',Roi)]+[(n,C.c_int) for n in ('valid','faces','eye_count')]

def check_files():
    dll=ROOT/'pc_runtime/model.dll'
    manifest=json.loads((ROOT/'pc_runtime/model_manifest.json').read_text(encoding='utf-8'))
    if C.sizeof(C.c_void_p)!=8:raise RuntimeError('请使用 64 位 Python。')
    if manifest['abi']!=1 or hashlib.sha256(dll.read_bytes()).hexdigest()!=manifest['dll_sha256']:
        raise RuntimeError('模型 DLL 与记录不一致，请运行 tools/build_pc_model.py 重建。')
    for name,digest in manifest['sources'].items():
        if hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=digest:
            raise RuntimeError('检测源码已改变，请重建 PC 模型：'+name)
    return dll

class Detector:
    # haar.c uses static buffers: serialize even if multiple adapters are created.
    lock=threading.Lock()
    def __init__(self):
        self.lib=C.CDLL(str(check_files()))
        self.lib.pc_abi_value.argtypes=[C.c_uint]
        self.lib.pc_abi_value.restype=C.c_uint
        expected=[C.sizeof(Roi),C.sizeof(Box),C.sizeof(Loc)]+[getattr(Loc,n).offset for n,_ in Loc._fields_]
        actual=[self.lib.pc_abi_value(i) for i in range(len(expected))]
        if actual!=expected:raise RuntimeError('模型与 Python 数据结构不匹配，请重新构建。')
        self.lib.auto_localize.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32,C.POINTER(Loc)]
        self.lib.auto_localize.restype=C.c_int

    def detect(self,frame):
        if not isinstance(frame,np.ndarray) or frame.dtype!=np.uint8 or frame.ndim!=3 or frame.shape[2]!=3:
            raise ValueError('需要 8 位 BGR 彩色图像。')
        h,w=frame.shape[:2]
        if min(w,h)<64 or max(w,h)>4096:raise ValueError('图像宽高需要在 64–4096 像素之间。')
        frame=np.ascontiguousarray(frame)
        loc=Loc()
        with self.lock:
            start=time.perf_counter()
            ok=self.lib.auto_localize(frame.ctypes.data,frame.strides[0],w,h,C.byref(loc))
            elapsed=(time.perf_counter()-start)*1000
        boxes={key:[getattr(getattr(loc,key),v) for v in ('x','y','w','h')]
               for key in ('face','left','right')}
        if ok:
            for x,y,bw,bh in boxes.values():
                if bw<=0 or bh<=0 or x+bw>w or y+bh>h:raise RuntimeError('模型返回越界框。')
        return dict(valid=bool(ok),faces=loc.faces,eye_count=loc.eye_count,host_ms=elapsed,
                    width=w,height=h,**boxes)

def fit_input(frame):
    if frame is None:raise ValueError('没有读取到图像。')
    h,w=frame.shape[:2]
    scale=min(1,1280/w,720/h)
    return cv2.resize(frame,(round(w*scale),round(h*scale))) if scale<1 else frame.copy()

def load_image(path):
    image=cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_COLOR)
    if image is None:raise ValueError('无法读取图片，请选择 PNG、JPG 或 BMP 文件。')
    return fit_input(image)

def annotate(frame,result):
    output=frame.copy()
    if result['valid']:
        for key in ('face','left','right'):
            x,y,w,h=result[key]
            cv2.rectangle(output,(x,y),(x+w-1,y+h-1),(0,220,255) if key=='face' else (60,240,60),2)
    return output

"""Metric stereo on ARM without importing its incompatible Python cv2 extension.

Calibration is prepared on the PC for the exact passive observer sampling mode.
The two sensor exposures remain independent; use static calibration/targets.
"""
import ctypes as C
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import zipfile
import numpy as np

CAPTURE_MODE='z20-observer-q4-bgr-gray160x180-completion5ms-v2'


def _json(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,allow_nan=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def prepare_pair(pixels):
    if not isinstance(pixels,np.ndarray) or pixels.dtype!=np.uint8 or pixels.shape!=(180,320,3):
        raise ValueError('expected exact quarter-sampled observer BGR pixels')
    bgr=pixels.astype(np.uint32)
    gray=((bgr[:,:,0]*1868+bgr[:,:,1]*9617+bgr[:,:,2]*4899+8192)>>14).astype(np.uint8)
    return np.ascontiguousarray(np.stack((gray[:,:160],gray[:,160:])))


def record_pair(directory,pair,*,sequence,captured_ns):
    if pair.shape!=(2,180,160) or pair.dtype!=np.uint8:raise ValueError('expected calibrated capture geometry')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/'pairs.json'
    value=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(capture_mode=CAPTURE_MODE,pairs=[])
    if value['capture_mode']!=CAPTURE_MODE:raise ValueError('existing capture mode differs')
    key='%d-%d'%(captured_ns,sequence)
    names=[name+'-'+key+'.pgm' for name in ('left','right')]
    if any((directory/name).exists() for name in names):raise ValueError('calibration pair already exists')
    for name,image in zip(names,pair):(directory/name).write_bytes(b'P5\n160 180\n255\n'+image.tobytes())
    value['pairs'].append(dict(sequence=sequence,captured_ns=captured_ns,left=names[0],right=names[1]))
    _json(path,value);return path


class NativeMatcher:
    def __init__(self,path):
        self.library=C.CDLL(str(Path(path).resolve()))
        byte=C.POINTER(C.c_ubyte);floats=C.POINTER(C.c_float)
        self.function=self.library.z_stereo_bm
        self.function.argtypes=[C.c_int]*4+[byte,byte,floats,floats]
        self.function.restype=C.c_int

    def __call__(self,left,right,maps,disparities,block_size):
        output=np.empty(left.shape,np.float32)
        status=self.function(left.shape[1],left.shape[0],disparities,block_size,
            left.ctypes.data_as(C.POINTER(C.c_ubyte)),right.ctypes.data_as(C.POINTER(C.c_ubyte)),
            maps.ctypes.data_as(C.POINTER(C.c_float)),output.ctypes.data_as(C.POINTER(C.c_float)))
        if status:raise RuntimeError('native stereo failed: %d'%status)
        return output


@dataclass
class DepthFrame:
    distance_m: object
    valid_points: int
    disparity: object
    xyz: object
    valid_mask: object


class BoardStereo:
    def __init__(self,folder,*,matcher=None,library=None):
        folder=Path(folder);self.metadata=json.loads((folder/'calibration.json').read_text(encoding='utf-8'))
        meta=self.metadata
        if (meta.get('format')!='z20-board-stereo-v1' or meta.get('capture_mode')!=CAPTURE_MODE
                or meta.get('image_size')!=[160,180] or meta.get('units')!='m'
                or not isinstance(meta.get('calibration_id'),str) or len(meta['calibration_id'])!=64
                or any(c not in '0123456789abcdef' for c in meta['calibration_id'])):
            raise ValueError('calibration does not match observer geometry/metric provenance')
        path=folder/'maps.npz'
        if path.stat().st_size>2*1024*1024 or hashlib.sha256(path.read_bytes()).hexdigest()!=meta.get('maps_sha256'):
            raise ValueError('calibration maps hash mismatch')
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist())>2*1024*1024:
                raise ValueError('expanded calibration maps exceed limit')
        with np.load(str(path),allow_pickle=False) as data:
            self.maps=np.ascontiguousarray(data['maps'],np.float32);self.q=np.asarray(data['q'],np.float64)
        if (self.maps.shape!=(4,180,160) or self.q.shape!=(4,4)
                or not np.isfinite(self.maps).all() or not np.isfinite(self.q).all()):
            raise ValueError('invalid rectification maps')
        self.matcher=matcher if matcher is not None else NativeMatcher(library or folder/'libz20_stereo.so')

    def process(self,pair,*,capture_mode,roi=(64,74,32,32)):
        if capture_mode!=CAPTURE_MODE or pair.shape!=(2,180,160) or pair.dtype!=np.uint8:
            raise ValueError('stereo input does not match calibration')
        x,y,w,h=roi
        if any(type(v) is not int for v in roi) or min(x,y)<0 or min(w,h)<1 or x+w>160 or y+h>180:
            raise ValueError('measurement ROI outside image')
        disparity=np.asarray(self.matcher(*np.ascontiguousarray(pair),self.maps,32,15),np.float32)
        if disparity.shape!=(180,160):raise ValueError('invalid native disparity geometry')
        yy,xx=np.mgrid[:180,:160]
        homogeneous=np.stack((xx,yy,disparity,np.ones_like(disparity)),axis=-1) @ self.q.T
        with np.errstate(divide='ignore',invalid='ignore'):
            xyz=(homogeneous[:,:,:3]/homogeneous[:,:,3:4]).astype(np.float32)
        valid=(disparity>0)&np.isfinite(xyz).all(2)&(xyz[:,:,2]>=.1)&(xyz[:,:,2]<=10.)
        z=xyz[y:y+h,x:x+w,2][valid[y:y+h,x:x+w]]
        return DepthFrame(float(np.median(z)) if z.size>=10 else None,int(z.size),disparity,xyz,valid)

    def export(self,directory,result,*,sequence):
        if type(sequence) is not int or sequence<0:raise ValueError('invalid frame sequence')
        artifact_id='frame_%d'%sequence;folder=Path(directory)/artifact_id;folder.mkdir(parents=True,exist_ok=True)
        points=result.xyz[result.valid_mask];points=points[np.isfinite(points).all(1)]
        with (folder/'cloud.ply.tmp').open('wb') as stream:
            stream.write(('ply\nformat binary_little_endian 1.0\ncomment units metre\nelement vertex %d\n'%len(points)).encode('ascii'))
            stream.write(b'property float x\nproperty float y\nproperty float z\nend_header\n')
            stream.write(points.astype('<f4',copy=False).tobytes())
        (folder/'cloud.ply.tmp').replace(folder/'cloud.ply')
        value=dict(artifact_id=artifact_id,points=len(points),metric=True,units='m',
            calibration_id=self.metadata['calibration_id'],capture_mode=CAPTURE_MODE)
        _json(folder/'snapshot.json',dict(value,sha256=hashlib.sha256((folder/'cloud.ply').read_bytes()).hexdigest()))
        return value

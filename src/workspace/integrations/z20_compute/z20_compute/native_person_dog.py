"""ARM adapter to video decode, ORB registration and overlay rendering."""
import ctypes as C
from pathlib import Path

import numpy as np


class NativeMedia:
    def __init__(self,library):
        self.library=C.CDLL(str(Path(library).resolve()))
        self.photos=self.video=None
        lib=self.library
        byte=C.POINTER(C.c_ubyte);double=C.POINTER(C.c_double)
        lib.z_photos_open.argtypes=[C.c_char_p]*3;lib.z_photos_open.restype=C.c_void_p
        lib.z_photos_close.argtypes=[C.c_void_p];lib.z_photos_close.restype=None
        lib.z_photos_match.argtypes=[C.c_void_p,byte,C.c_int,C.c_int,double,C.POINTER(C.c_int)]
        lib.z_photos_match.restype=C.c_int
        lib.z_video_open.argtypes=[C.c_char_p];lib.z_video_open.restype=C.c_void_p
        lib.z_video_next.argtypes=[C.c_void_p,byte,double];lib.z_video_next.restype=C.c_int
        lib.z_video_close.argtypes=[C.c_void_p];lib.z_video_close.restype=None
        lib.z_render.argtypes=[byte,C.c_int,C.c_int,byte,double,double,C.c_int,byte]
        lib.z_render.restype=C.c_int

    @staticmethod
    def _image(rgb):
        if not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:
            raise ValueError('expected RGB uint8 pixels')
        return np.ascontiguousarray(rgb)

    @staticmethod
    def _pointer(rgb):return rgb.ctypes.data_as(C.POINTER(C.c_ubyte))

    def load_photos(self,paths):
        if len(paths)!=3:raise ValueError('three photo paths required')
        if self.photos:self.library.z_photos_close(self.photos)
        self.photos=self.library.z_photos_open(*(str(p).encode() for p in paths))
        if not self.photos:raise RuntimeError('native photo initialization failed')

    def match(self,rgb):
        if not self.photos:raise RuntimeError('photo references not loaded')
        image=self._image(rgb);h=(C.c_double*9)();count=C.c_int()
        scene=self.library.z_photos_match(self.photos,self._pointer(image),image.shape[1],
                                         image.shape[0],h,C.byref(count))
        if scene==-2:raise RuntimeError('native photo matching failed')
        return dict(scene_id=None if scene<0 else scene,
                    homography=None if scene<0 else np.array(h).reshape(3,3).tolist(),
                    inliers=count.value,state='unrecognized' if scene<0 else 'registered_photo')

    def open_video(self,path):
        if self.video:self.library.z_video_close(self.video)
        self.video=self.library.z_video_open(str(path).encode())
        if not self.video:raise RuntimeError('native source video decoding unavailable')

    def next_video(self):
        if not self.video:raise RuntimeError('video not open')
        image=np.zeros((480,640,3),np.uint8);timestamp=C.c_double()
        state=self.library.z_video_next(self.video,self._pointer(image),C.byref(timestamp))
        if state<0:raise RuntimeError('native source video decode failed')
        return None if state==0 else (image,timestamp.value)

    def render(self,rgb,background,boxes=None,geometry=None):
        image=self._image(rgb)
        if len(background)!=1280*720*3:raise ValueError('expected RGB720p background')
        bg=np.frombuffer(background,np.uint8).reshape(720,1280,3).copy()
        output=np.empty_like(bg)
        b=np.ascontiguousarray([] if boxes is None else boxes,dtype=np.float64).reshape(-1)
        g=np.ascontiguousarray([] if geometry is None else geometry,dtype=np.float64).reshape(-1)
        valid=boxes is not None and geometry is not None
        if valid and (b.shape!=(8,) or g.shape!=(3,) or not np.isfinite(b).all() or not np.isfinite(g).all()):
            raise ValueError('expected two finite boxes and three geometry values')
        result=self.library.z_render(self._pointer(image),image.shape[1],image.shape[0],self._pointer(bg),
            b.ctypes.data_as(C.POINTER(C.c_double)),g.ctypes.data_as(C.POINTER(C.c_double)),int(valid),
            self._pointer(output))
        if result:raise RuntimeError('native overlay rendering failed')
        return output

    def close(self):
        if self.photos:self.library.z_photos_close(self.photos)
        if self.video:self.library.z_video_close(self.video)
        self.photos=self.video=None

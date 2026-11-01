"""OpenCV C ABI for the original ARM userspace, avoiding a Python cv2 dependency."""
import ctypes as C
import numpy as np
from pathlib import Path
from .visual_wire import jpeg_dimensions


class NativeJPEG:
    def __init__(self,path):
        self.lib=C.CDLL(str(Path(path).resolve()))
        self.lib.z_visual_decode.argtypes=[C.POINTER(C.c_ubyte),C.c_int,C.POINTER(C.c_ubyte)]
        self.lib.z_visual_decode.restype=C.c_int

    def __call__(self,jpeg):
        jpeg_dimensions(jpeg)
        source=np.frombuffer(jpeg,np.uint8)
        result=np.empty((720,1280,3),np.uint8)
        pointer=lambda a:a.ctypes.data_as(C.POINTER(C.c_ubyte))
        if self.lib.z_visual_decode(pointer(source),len(jpeg),pointer(result)):
            raise ValueError('native JPEG decoding failed')
        return result

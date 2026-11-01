"""Compare the same C++ source used by HLS against independent OpenCV output."""
import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import cv2
import numpy as np
from vision_demo.processing import ReferenceProcessor
from vision_demo.session import MODES

ROOT = Path(__file__).resolve().parents[1]


class HardwareAlgorithmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        path = Path(cls.temp.name)/('vision.dll' if os.name == 'nt' else 'vision.so')
        compiler = os.environ.get('CXX', 'C:/mingw64/mingw64/bin/g++.exe' if os.name == 'nt' else 'g++')
        result = subprocess.run([compiler, '-std=c++11', '-O2', '-shared', '-static-libgcc', '-static-libstdc++',
                                 str(ROOT/'hls/vision_core.cpp'), '-o', str(path)], capture_output=True, text=True)
        if result.returncode: raise AssertionError(result.stdout+result.stderr)
        cls.lib = ctypes.CDLL(str(path))
        cls.run_core = cls.lib.vision_core
        pointer = ctypes.POINTER(ctypes.c_uint32)
        cls.run_core.argtypes = [pointer, pointer, pointer] + [ctypes.c_uint32]*5
        cls.run_core.restype = ctypes.c_uint32

    @classmethod
    def tearDownClass(cls):
        if os.name == 'nt':
            import _ctypes
            _ctypes.FreeLibrary(cls.lib._handle)
        cls.run_core = cls.lib = None
        cls.temp.cleanup()

    def run_image(self, rgb, mode, history, reset):
        rgb32 = rgb.astype(np.uint32)
        packed = np.ascontiguousarray((rgb32[...,0]<<16)|(rgb32[...,1]<<8)|rgb32[...,2])
        output = np.zeros_like(packed)
        args = [a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)) for a in (packed,output,history)]
        code = self.run_core(*args, rgb.shape[1], rgb.shape[0], mode, int(reset), 127)
        self.assertEqual(code, 0)
        return np.stack(((output>>16)&255,(output>>8)&255,output&255),axis=-1).astype(np.uint8)

    def test_all_ten_modes_and_temporal_frames_match_reference(self):
        rng = np.random.default_rng(20261019)
        for mode, (name, _) in enumerate(MODES):
            reference = ReferenceProcessor()
            history = np.full((12,16), 0xFFFFFFFF, dtype=np.uint32)
            for step in range(3):
                rgb = rng.integers(0,256,(12,16,3),dtype=np.uint8)
                with self.subTest(mode=name, frame=step):
                    actual = self.run_image(rgb, mode, history, step==0)
                    expected = reference.process(rgb, name, reset=step==0)
                    np.testing.assert_array_equal(actual, expected)

    def test_thin_images_and_constant_histogram_match_reference(self):
        for height,width in [(1,1),(1,7),(7,1),(2,2)]:
            rgb=np.full((height,width,3),113,np.uint8)
            for mode,(name,_) in enumerate(MODES):
                history=np.full((height,width),0xFFFFFFFF,np.uint32)
                with self.subTest(shape=(height,width),mode=name):
                    np.testing.assert_array_equal(self.run_image(rgb,mode,history,True),
                        ReferenceProcessor().process(rgb,name,reset=True))


if __name__ == '__main__': unittest.main()

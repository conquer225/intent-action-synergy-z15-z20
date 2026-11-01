import ctypes
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.npu import QuantizedMLP
from test_npu import worked_model


@unittest.skipUnless(shutil.which("g++"), "host C++ compiler unavailable")
class HlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.directory.name)/("mlp.dll" if sys.platform == "win32" else "mlp.so")
        source = Path(__file__).resolve().parents[1]/"hardware/hls/mlp.cpp"
        subprocess.run(["g++", "-std=c++14", "-O2", "-shared", "-static-libgcc", "-static-libstdc++",
                        str(source), "-o", str(cls.binary)], check=True, capture_output=True, text=True)
        cls.library = ctypes.CDLL(str(cls.binary))
        cls.core = cls.library.z20_mlp
        cls.core.argtypes = [ctypes.c_void_p]*6 + [ctypes.c_uint, ctypes.c_uint]
        cls.core.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        # Loaded DLLs remain mapped on Windows; TemporaryDirectory retries later.
        if sys.platform == "win32":
            import _ctypes
            _ctypes.FreeLibrary(cls.library._handle)
        cls.directory.cleanup()

    def run_core(self, model, values):
        arrays = [values, model.w1, model.b1, model.w2, model.b2, np.zeros(3, dtype=np.int32)]
        status = self.core(*[a.ctypes.data for a in arrays], len(values), model.hidden_shift)
        self.assertEqual(status, 0)
        return arrays[-1]

    def test_hand_calculated_output_and_all_four_input_sizes(self):
        self.assertEqual(self.run_core(worked_model(), np.array([3, -2], np.int8)).tolist(), [3, 125, -3])
        rng = np.random.default_rng(7)
        for dimension in [20, 40, 180, 1024]:
            for shift in [0, 1, 7, 31]:
                model = QuantizedMLP(rng.integers(-128, 128, (32, dimension), dtype=np.int8),
                                     rng.integers(-5000, 5000, 32, dtype=np.int32),
                                     rng.integers(-128, 128, (3, 32), dtype=np.int8),
                                     rng.integers(-100, 100, 3, dtype=np.int32), hidden_shift=shift)
                values = rng.integers(-128, 128, dimension, dtype=np.int8)
                with self.subTest(dimension=dimension, shift=shift):
                    np.testing.assert_array_equal(self.run_core(model, values), model.infer(values))


if __name__ == "__main__":
    unittest.main()

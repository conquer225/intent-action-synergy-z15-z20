import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from z20_compute.npu import QuantizedMLP


def worked_model():
    w1 = np.zeros((32, 2), dtype=np.int8)
    w1[:4] = [[2, 1], [-1, 2], [100, -100], [1, -1]]
    b1 = np.zeros(32, dtype=np.int32)
    b1[1] = 1
    w2 = np.zeros((3, 32), dtype=np.int8)
    w2[0, 0], w2[1, 1:3], w2[2, 3] = 1, [1, 1], -1
    return QuantizedMLP(w1, b1, w2, np.array([1, -2, 0], dtype=np.int32), hidden_shift=1)


class NpuTests(unittest.TestCase):
    def test_worked_dense_relu_rounding_and_saturation(self):
        # Hidden values are 2, 0, 127 (saturated), 3 (2.5 rounds away).
        # The final three sums are 2+1, 0+127-2, -3.
        self.assertEqual(worked_model().infer(np.array([3, -2], dtype=np.int8)).tolist(), [3, 125, -3])


if __name__ == "__main__":
    unittest.main()

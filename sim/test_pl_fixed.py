"""Worked numerical contracts for the programmable-logic extensions."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/workspace/integrations'))
from pl_accel.fixed import log2_q12, population_variance, round_shift, saturate24


class FixedPointContract(unittest.TestCase):
    def test_symmetric_rounding_and_stage_saturation(self):
        self.assertEqual([round_shift(x, 1) for x in (3, -3, 2, -2, 0)], [2, -2, 1, -1, 0])
        self.assertEqual(round_shift(-17, 0), -17)
        self.assertEqual(saturate24(1 << 24), 8388607)
        self.assertEqual(saturate24(-(1 << 24)), -8388608)

    def test_population_variance_preserves_fractional_mean(self):
        # [1, 2] has mean 1.5 and variance .25: integer variance is zero.
        self.assertEqual(population_variance(3, 5, 2), 0)
        # [0, 2, 4, 6] has mean 3 and population variance 5.
        self.assertEqual(population_variance(12, 56, 4), 5)
        self.assertEqual(population_variance(-12, 56, 4), 5)
        self.assertEqual(population_variance(8388607 * 1024, 8388607**2 * 1024, 1024), 0)

    def test_logarithm_powers_and_mantissa_error(self):
        for power in range(48):
            self.assertEqual(log2_q12(1 << power), power * 4096)
        for value in (3, 7, 13, 1001, 123456789, (1 << 47) - 1):
            self.assertLessEqual(abs(log2_q12(value) / 4096 - math.log2(value)), .006)


if __name__ == '__main__':
    unittest.main()

import unittest

import numpy as np
from scipy.signal import butter

from fixed_sos import FixedSOS, quantize, rounded_shift, DATA_BITS, DATA_FRAC


class FixedSOSTest(unittest.TestCase):
    def test_rounding_and_rejection(self):
        self.assertEqual([rounded_shift(x, 2) for x in (-7,-6,-5,0,5,6,7)], [-2,-2,-1,0,1,2,2])
        with self.assertRaises(ValueError):
            quantize([np.nan], DATA_FRAC, DATA_BITS)
        with self.assertRaises(OverflowError):
            quantize([2**23], DATA_FRAC, DATA_BITS)

    def test_channel_isolation_chunking_and_reset(self):
        sos = butter(4, (1,45), fs=250, btype='bandpass', output='sos')
        x = np.zeros((1000,8), dtype=np.int64)
        x[0,3] = 1000 << DATA_FRAC
        a, b = FixedSOS(sos), FixedSOS(sos)
        y = a.process_quantized(x)
        self.assertTrue(np.array_equal(y, np.concatenate([b.process_quantized(x[:123]),b.process_quantized(x[123:])])) )
        self.assertTrue(np.all(y[:, [0,1,2,4,5,6,7]] == 0))
        a.reset()
        self.assertTrue(np.array_equal(y,a.process_quantized(x)))


if __name__ == '__main__':
    unittest.main()

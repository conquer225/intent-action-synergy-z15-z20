"""Bit-exact DF-II-transposed prototype. Not imported by the live service."""
import numpy as np

DATA_BITS = 40
DATA_FRAC = 16
COEFF_BITS = 34
COEFF_FRAC = 31
ACC_BITS = 76


def rounded_shift(value, shift):
    """Nearest integer, exact halves away from zero (also for negatives)."""
    if value < 0:
        return -((-value + (1 << (shift - 1))) >> shift)
    return (value + (1 << (shift - 1))) >> shift


def quantize(values, frac, bits):
    scaled = np.asarray(values, dtype=np.float64) * (1 << frac)
    if not np.isfinite(scaled).all():
        raise ValueError('Nonfinite input')
    rounded = np.copysign(np.floor(np.abs(scaled) + .5), scaled)
    if np.any(rounded < -(1 << (bits-1))) or np.any(rounded > (1 << (bits-1))-1):
        raise OverflowError('Input exceeds fixed-point contract; do not silently clip')
    return rounded.astype(np.int64)


class FixedSOS:
    def __init__(self, sos, channels=8, coeff_bits=COEFF_BITS, coeff_frac=COEFF_FRAC):
        sos = np.asarray(sos, dtype=np.float64)
        if sos.ndim != 2 or sos.shape[1] != 6 or not np.all(sos[:, 3] == 1):
            raise ValueError('Normalized SOS required')
        self.coeff_frac = coeff_frac
        self.coeff = quantize(sos[:, [0, 1, 2, 4, 5]], coeff_frac, coeff_bits).tolist()
        self.channels = channels
        self.reset()

    def reset(self):
        self.z = [[[0, 0] for _ in range(self.channels)] for _ in self.coeff]
        self.saturations = 0
        self.max_acc_abs = 0

    def narrow(self, accumulator):
        if not -(1 << (ACC_BITS-1)) <= accumulator < (1 << (ACC_BITS-1)):
            raise OverflowError('Accumulator overflow')
        self.max_acc_abs = max(self.max_acc_abs, abs(accumulator))
        value = rounded_shift(accumulator, self.coeff_frac)
        low, high = -(1 << (DATA_BITS-1)), (1 << (DATA_BITS-1))-1
        if value < low or value > high:
            self.saturations += 1
            return max(low, min(value, high))
        return value

    def process_quantized(self, values):
        values = np.asarray(values)
        if values.ndim != 2 or values.shape[1] != self.channels or values.dtype.kind not in 'iu':
            raise ValueError('Integer samples x channels required')
        if np.any(values < -(1 << (DATA_BITS-1))) or np.any(values >= (1 << (DATA_BITS-1))):
            raise OverflowError('Input outside signed data width')
        result = np.empty(values.shape, dtype=np.int64)
        for i, row in enumerate(values):
            for channel, item in enumerate(row):
                x = int(item)
                for stage, (b0, b1, b2, a1, a2) in enumerate(self.coeff):
                    s1, s2 = self.z[stage][channel]
                    y = self.narrow(b0*x + (s1 << self.coeff_frac))
                    z1 = self.narrow(b1*x - a1*y + (s2 << self.coeff_frac))
                    z2 = self.narrow(b2*x - a2*y)
                    self.z[stage][channel] = [z1, z2]
                    x = y
                result[i, channel] = x
        return result

"""Integer arithmetic shared by model export and the independent PL reference."""
import math
import numpy as np

LOG2_LUT = tuple(round(math.log2(1 + i / 256) * 4096) for i in range(256))


def quantize_samples_uv(values):
    values = np.asarray(values, np.float64)
    if not np.isfinite(values).all() or np.max(np.abs(values), initial=0) > 32767:
        raise ValueError('microvolt samples must fit the signed Q8 sample range')
    return (np.sign(values)*np.floor(np.abs(values)*256+.5)).astype(np.int32)


def round_shift(value, bits):
    """Round ties away from zero, with no signed-right-shift dependency."""
    if not 0 <= bits <= 62:
        raise ValueError('shift must be in 0..62')
    value = int(value)
    magnitude = (abs(value) + (1 << (bits - 1))) >> bits if bits else abs(value)
    return -magnitude if value < 0 else magnitude


def saturate24(value):
    return max(-8388608, min(8388607, int(value)))


def population_variance(total, squares, count):
    """Floor exact population variance using bounded 64-bit intermediates.

    For <=1024 signed-24-bit observations the centered sum is below 2**58.
    Dividing the mean first avoids constructing count*squares or total**2.
    """
    if not 1 <= count <= 1024:
        raise ValueError('variance count must be in 1..1024')
    total, squares = int(total), int(squares)
    mean = abs(total) // count * (-1 if total < 0 else 1)
    residual = total - mean * count
    centered = squares - 2 * mean * total + mean * mean * count
    value, remainder = divmod(centered, count)
    return max(0, value - (remainder * count < residual * residual))


def log2_q12(value):
    """Unsigned integer log2, Q12; floor-one input and eight mantissa bits."""
    value = max(1, int(value))
    exponent = value.bit_length() - 1
    mantissa = ((value - (1 << exponent)) << 8) >> exponent
    return exponent * 4096 + LOG2_LUT[mantissa]

"""Integer reference for the shared D->32 ReLU->3 HLS core."""
import numpy as np


class QuantizedMLP:
    def __init__(self, w1, b1, w2, b2, *, hidden_shift):
        self.w1, self.b1, self.w2, self.b2 = [np.array(a, copy=True) for a in (w1, b1, w2, b2)]
        if (self.w1.ndim != 2 or self.w1.shape[0] != 32 or not 1 <= self.w1.shape[1] <= 1024
                or self.b1.shape != (32,) or self.w2.shape != (3, 32) or self.b2.shape != (3,)
                or self.w1.dtype != np.int8 or self.w2.dtype != np.int8
                or self.b1.dtype != np.int32 or self.b2.dtype != np.int32
                or type(hidden_shift) is not int or not 0 <= hidden_shift <= 31):
            raise ValueError("expected int8 weights/int32 biases for D->32->3")
        self.hidden_shift = hidden_shift
        for w, b, maximum in [(self.w1, self.b1, 128), (self.w2, self.b2, 127)]:
            bound = np.abs(w.astype(np.int64)).sum(axis=1)*maximum + np.abs(b.astype(np.int64))
            if np.any(bound > np.iinfo(np.int32).max):
                raise ValueError("model can overflow INT32 accumulation")
        for a in (self.w1, self.b1, self.w2, self.b2):
            a.flags.writeable = False

    def infer(self, values):
        values = np.asarray(values)
        if values.dtype != np.int8 or values.shape != (self.w1.shape[1],):
            raise ValueError("input shape/dtype differs from integer model")
        hidden = self.w1.astype(np.int64) @ values.astype(np.int64) + self.b1
        if self.hidden_shift:
            magnitude = (np.abs(hidden) + (1 << (self.hidden_shift-1))) >> self.hidden_shift
            hidden = np.where(hidden < 0, -magnitude, magnitude)
        hidden = np.clip(hidden, 0, 127)
        return (self.w2.astype(np.int64) @ hidden + self.b2).astype(np.int32)

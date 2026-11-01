"""Reuse JSON rows only when both rounded waveform overlaps are identical."""
import json

import numpy as np


class WaveformJSONCache:
    def __init__(self):
        self.arrays = None
        self.rows = None
        self.index = None
        self.reused_rows = 0

    def encode(self, samples, raw_samples, sample_index):
        arrays = tuple(np.round(np.asarray(values), 3) for values in (samples, raw_samples))
        if (any(values.ndim != 2 or values.shape[1] != 8 for values in arrays)
                or arrays[0].shape != arrays[1].shape):
            raise ValueError('Display waveforms must have matching eight-channel shapes')
        if any(not np.all(np.isfinite(values)) for values in arrays):
            raise ValueError('Nonfinite display waveform')
        count = len(arrays[0])
        delta = sample_index - self.index if self.index is not None else count + 1
        reuse = (self.arrays is not None and 0 <= delta <= count
                 and all(before.shape == after.shape and
                         np.array_equal(before[delta:], after[:count-delta])
                         for before, after in zip(self.arrays, arrays)))
        self.reused_rows = count - delta if reuse else 0
        rows = []
        for lane, values in enumerate(arrays):
            retained = self.rows[lane][delta:] if reuse else []
            added = [json.dumps(row.tolist(), separators=(',', ':'), allow_nan=False)
                     for row in values[self.reused_rows:]]
            rows.append(retained + added)
        self.arrays, self.rows, self.index = arrays, rows, sample_index
        return tuple('[' + ','.join(lane) + ']' for lane in rows)

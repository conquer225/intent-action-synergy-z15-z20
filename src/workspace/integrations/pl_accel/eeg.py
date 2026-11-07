"""Eight-channel fixed-point filter-bank CSP/SVM and its model contract."""
import hashlib
import json
from pathlib import Path

import numpy as np

from .fixed import log2_q12, population_variance, round_shift, saturate24

CHANNELS = ('F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2')
BANDS = ((8., 16.), (16., 24.), (24., 32.))
MAGIC = 0x46424331
PARAM_WORDS = 94
MAX_WINDOW = 1024


def _integers(values, shape, bound, name):
    array = np.asarray(values)
    if array.shape != shape or array.dtype.kind not in 'iu':
        raise ValueError(name + ' shape/integer contract')
    if any(abs(int(x)) > bound for x in array.flat):
        raise ValueError(name + ' magnitude contract')
    result = array.astype(np.int32, copy=True)
    result.flags.writeable = False
    return result


class EEGModel:
    def __init__(self, sos_q28, csp_q14, svm_q12, bias_q24, *, window=500, hop=125,
                 metadata=None):
        if type(window) is not int or type(hop) is not int or not 4 <= window <= MAX_WINDOW or not 1 <= hop <= window:
            raise ValueError('window/hop contract')
        if type(bias_q24) is not int or abs(bias_q24) >= 1 << 55:
            raise ValueError('SVM bias contract')
        self.sos = _integers(sos_q28, (3, 2, 5), (1 << 31) - 1, 'SOS')
        for section in self.sos.reshape(-1, 5):
            if np.max(np.abs(np.roots([1., int(section[3]) / 2**28, int(section[4]) / 2**28]))) >= 1:
                raise ValueError('SOS poles must be strictly stable')
        self.csp = _integers(csp_q14, (3, 2, 8), 1 << 20, 'CSP')
        self.svm = _integers(svm_q12, (6,), 1 << 23, 'SVM')
        self.bias, self.window, self.hop = bias_q24, window, hop
        self.metadata = json.loads(json.dumps(metadata or {}, allow_nan=False))

    def parameter_words(self):
        words = [MAGIC, 1, self.window, self.hop, 8, 3, 2, 250]
        words += self.sos.ravel().tolist() + self.csp.ravel().tolist() + self.svm.tolist()
        bias = self.bias & ((1 << 64) - 1)
        words += [bias & 0xffffffff, bias >> 32]
        return np.asarray([x if x < 1 << 31 else x - (1 << 32) for x in words], np.int32)

    def to_dict(self):
        return dict(schema='intent-fbcsp-v1', channels=list(CHANNELS), rate_hz=250,
                    bands_hz=BANDS, window=self.window, hop=self.hop,
                    sample_q=8, sos_q=28, csp_q=14, feature_q=12, svm_q=12,
                    normalization='per_band_pair_log2_v1',
                    sos_q28=self.sos.tolist(), csp_q14=self.csp.tolist(),
                    svm_q12=self.svm.tolist(), bias_q24=self.bias, metadata=self.metadata)

    @property
    def identity(self):
        return hashlib.sha256(self.parameter_words().astype('<i4').tobytes()).hexdigest()

    @classmethod
    def from_dict(cls, data):
        if (data.get('schema') != 'intent-fbcsp-v1' or tuple(data.get('channels', ())) != CHANNELS
                or data.get('rate_hz') != 250 or data.get('normalization') != 'per_band_pair_log2_v1'
                or [data.get(k) for k in ('sample_q', 'sos_q', 'csp_q', 'feature_q', 'svm_q')] != [8, 28, 14, 12, 12]
                or tuple(map(tuple, data.get('bands_hz', ()))) != BANDS):
            raise ValueError('incompatible EEG model contract')
        return cls(data['sos_q28'], data['csp_q14'], data['svm_q12'], data['bias_q24'],
                   window=data['window'], hop=data['hop'], metadata=data.get('metadata'))

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2,
                                        allow_nan=False) + '\n', encoding='utf-8')


class EEGReference:
    """Sequential sample reference; persistent filters and exact sliding moments."""
    def __init__(self, model):
        self.model = model
        self.reset()

    def reset(self):
        self.history = np.zeros((3, 2, 8, 4), np.int64)
        self.ring = np.zeros((6, self.model.window), np.int32)
        self.totals, self.squares = [0] * 6, [0] * 6
        self.samples, self.windows, self.clipped = 0, 0, 0

    def _sat(self, value):
        out = saturate24(value)
        self.clipped += out != value
        return out

    def feed(self, samples):
        values = np.asarray(samples)
        if values.ndim != 2 or values.shape[1] != 8 or values.dtype.kind not in 'iu':
            raise ValueError('expected sample-major integer Q8 rows with eight channels')
        if values.size and (np.min(values) < -8388608 or np.max(values) > 8388607):
            raise ValueError('input exceeds signed 24-bit sample contract')
        results = []
        for row in values:
            projected = []
            for band in range(3):
                filtered = []
                for channel in range(8):
                    x = int(row[channel])
                    for section in range(2):
                        b0, b1, b2, a1, a2 = map(int, self.model.sos[band, section])
                        x1, x2, y1, y2 = map(int, self.history[band, section, channel])
                        y = self._sat(round_shift(b0*x + b1*x1 + b2*x2 - a1*y1 - a2*y2, 28))
                        self.history[band, section, channel] = [x, x1, y, y1]
                        x = y
                    filtered.append(x)
                for component in range(2):
                    dot = sum(int(w)*x for w, x in zip(self.model.csp[band, component], filtered))
                    projected.append(self._sat(round_shift(dot, 14)))
            position = self.samples % self.model.window
            for index, value in enumerate(projected):
                old = int(self.ring[index, position])
                self.totals[index] += value - old
                self.squares[index] += value*value - old*old
                self.ring[index, position] = value
            self.samples += 1
            if self.samples >= self.model.window and (self.samples-self.model.window) % self.model.hop == 0:
                variances = [population_variance(s, ss, self.model.window)
                             for s, ss in zip(self.totals, self.squares)]
                features = []
                for band in range(3):
                    pair = [max(1, v) for v in variances[2*band:2*band+2]]
                    denominator = log2_q12(sum(pair))
                    features.extend(log2_q12(v)-denominator for v in pair)
                score = self.model.bias + sum(int(w)*x for w, x in zip(self.model.svm, features))
                self.windows += 1
                valid = self.clipped == 0 and all(sum(variances[2*b:2*b+2]) > 0 for b in range(3))
                results.append(dict(valid=valid, label=('right' if score >= 0 else 'left') if valid else None,
                                    class_id=int(score >= 0) if valid else None, score_q24=score,
                                    features=features, sample_count=self.samples, window_count=self.windows,
                                    clipped=self.clipped, model_sha256=self.model.identity,
                                    control_enabled=False))
        return results

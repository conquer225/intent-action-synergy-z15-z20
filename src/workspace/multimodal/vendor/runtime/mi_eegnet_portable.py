"""NumPy reference for a completed-window EEGNet; experimental, not production."""
import json
from pathlib import Path

import numpy as np

from mi_features import CHANNELS


class OfflineEEGNet:
    def __init__(self, path, *, allow_experimental=False):
        if not allow_experimental:
            raise ValueError('Unpromoted MI artifact requires explicit local experimental opt-in')
        with np.load(Path(path), allow_pickle=False) as data:
            self.metadata = json.loads(str(data['metadata'].item()))
            self.mean = data['source_mean'].astype(np.float64)
            self.scale = data['source_scale'].astype(np.float64)
            self.weights = {key: data[key].astype(np.float64) for key in data.files
                            if key not in ('metadata', 'source_mean', 'source_scale')}
        metadata = self.metadata
        if (metadata.get('channels') != list(CHANNELS) or metadata.get('window_samples') != 500
                or metadata.get('sample_rate_hz') != 250
                or metadata.get('status') != 'offline_plumbing_only'
                or any(metadata.get(key) is not False for key in
                       ('control_enabled', 'promotion_gate_passed', 'production_eligible'))
                or self.mean.shape != (8,) or self.scale.shape != (8,)
                or not np.isfinite(self.mean).all() or not np.isfinite(self.scale).all()
                or np.any(self.scale <= 0)):
            raise ValueError('Invalid experimental fixed-eight artifact')
        config = metadata['config']
        if any(config[key] != value for key, value in
               {'F1': 8, 'D': 2, 'F2': 16, 'temporal_kernel': 128,
                'separable_kernel': 16, 'pools': [4, 8], 'bn_eps': .001}.items()):
            raise ValueError('Unsupported EEGNet architecture')
        expected = {'temporal.weight': (8, 1, 1, 128), 'block1.1.weight': (16, 1, 8, 1),
                    'block2.1.weight': (16, 1, 1, 16), 'block2.2.weight': (16, 16, 1, 1),
                    'dense.weight': (2, 240), 'dense.bias': (2,)}
        for prefix, width in (('block1.0', 8), ('block1.2', 16), ('block2.3', 16)):
            for field in ('weight', 'bias', 'running_mean', 'running_var'):
                expected[prefix + '.' + field] = (width,)
        if set(expected) != set(self.weights):
            raise ValueError('Unexpected or missing learned tensors')
        for key, shape in expected.items():
            if self.weights[key].shape != shape or not np.isfinite(self.weights[key]).all():
                raise ValueError('Invalid tensor: ' + key)
        if any(np.any(self.weights[prefix + '.running_var'] < 0)
               for prefix in ('block1.0', 'block1.2', 'block2.3')):
            raise ValueError('Negative BN running variance')

    def _bn(self, values, prefix):
        w = self.weights
        width_shape = (1, -1) + (1,) * (values.ndim - 2)
        gain = w[prefix + '.weight'] / np.sqrt(w[prefix + '.running_var'] + .001)
        bias = w[prefix + '.bias'] - w[prefix + '.running_mean'] * gain
        return values * gain.reshape(width_shape) + bias.reshape(width_shape)

    @staticmethod
    def _elu_pool(values, width):
        values = np.where(values >= 0, values, np.expm1(np.minimum(values, 0)))
        stop = values.shape[-1] // width * width
        return values[..., :stop].reshape(*values.shape[:-1], -1, width).mean(axis=-1)

    def logits(self, waveforms):
        """Finite N×8×500 already CAR/notch/1–45/8–30-filtered waveforms."""
        values = np.asarray(waveforms)
        if (values.ndim != 3 or values.shape[1:] != (8, 500)
                or len(values) == 0 or not np.isfinite(values).all()):
            raise ValueError('Expected nonempty finite N×8×500 filtered waveform')
        # Match the training transform's FP32 rounding before portable arithmetic.
        values = ((values.astype(np.float64) - self.mean[None, :, None]) /
                  self.scale[None, :, None]).astype(np.float32).astype(np.float64)
        windows = np.lib.stride_tricks.sliding_window_view(
            np.pad(values, ((0, 0), (0, 0), (63, 64))), 128, axis=-1)
        temporal = np.einsum('nctk,fk->nfct', windows,
                             self.weights['temporal.weight'][:, 0, 0], optimize=True)
        temporal = self._bn(temporal, 'block1.0')
        spatial = np.einsum('nfct,fdc->nfdt', temporal,
                            self.weights['block1.1.weight'][:, 0, :, 0].reshape(8, 2, 8),
                            optimize=True).reshape(len(values), 16, 500)
        spatial = self._elu_pool(self._bn(spatial, 'block1.2'), 4)
        windows = np.lib.stride_tricks.sliding_window_view(
            np.pad(spatial, ((0, 0), (0, 0), (7, 8))), 16, axis=-1)
        depthwise = np.einsum('nftk,fk->nft', windows,
                              self.weights['block2.1.weight'][:, 0, 0], optimize=True)
        pointwise = np.einsum('nft,of->not', depthwise,
                              self.weights['block2.2.weight'][:, :, 0, 0], optimize=True)
        pooled = self._elu_pool(self._bn(pointwise, 'block2.3'), 8)
        logits = pooled.reshape(len(values), 240) @ self.weights['dense.weight'].T
        logits += self.weights['dense.bias']
        if not np.isfinite(logits).all():
            raise ValueError('Nonfinite logits; no prediction fallback')
        return logits

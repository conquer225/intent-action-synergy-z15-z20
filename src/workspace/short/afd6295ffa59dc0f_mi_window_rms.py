"""Whole-window MI scaling; one positive divisor preserves channel ratios."""
import numpy as np

TRANSFORM_ID = 'fixed8_shared_window_rms_v1'


def shared_window_rms(waveforms):
    """Normalize completed N×8×500 filtered windows, not raw quality signals."""
    values = np.asarray(waveforms, dtype=np.float64)
    if (values.ndim != 3 or values.shape[1:] != (8, 500) or len(values) == 0
            or not np.isfinite(values).all()):
        raise ValueError('Finite nonempty N x8 x500 completed windows required')
    scale = np.sqrt(np.mean(values * values, axis=(1, 2), keepdims=True))
    if not np.isfinite(scale).all() or np.any(scale <= 1e-12):
        raise ValueError('Degenerate MI energy; never normalize a flat window')
    return values / scale

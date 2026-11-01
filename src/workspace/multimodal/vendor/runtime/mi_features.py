"""Fixed-eight motor-imagery features shared by offline training and ARM inference.

Input is 250 Hz, eight-channel output from the existing CausalEEGFilter. No
channel substitution is allowed. These are 3-second cue-locked trial features,
not an unconstrained continuous mind-reading or control interface.
"""

import numpy as np
from scipy import signal


CHANNELS = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
RATE_HZ = 250
WINDOW_SAMPLES = 750
BANDS_HZ = ((8.0, 12.0), (18.0, 26.0))


def feature(window_uv):
    """Return 16 log Welch powers, ordered by band then fixed cap channel."""
    values = np.asarray(window_uv, dtype=np.float64)
    if values.shape != (WINDOW_SAMPLES, len(CHANNELS)) or not np.isfinite(values).all():
        raise ValueError(f"expected finite {WINDOW_SAMPLES} x 8 conditioned µV window")
    frequencies, spectrum = signal.welch(values, fs=RATE_HZ, nperseg=500,
                                          noverlap=250, axis=0, detrend="constant")
    return np.concatenate([
        np.log(np.maximum(spectrum[(frequencies >= low) & (frequencies <= high)].mean(axis=0),
                          1e-12))
        for low, high in BANDS_HZ
    ])


def relative_feature(task_uv, resting_uv):
    """Cue-locked ERD/ERS: task log power minus its preceding rest log power."""
    return feature(task_uv) - feature(resting_uv)

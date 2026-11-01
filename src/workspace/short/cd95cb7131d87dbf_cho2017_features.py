"""Causal per-original-epoch preprocessing; no synthetic continuous session."""
from pathlib import Path
import sys

import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pynq_guardianloop'))
from cyton_sqi import CausalEEGFilter
from mi_spatial import normalized_covariance


def _filtered_epoch(samples, cue_sample, protocol):
    values = np.asarray(samples, dtype=np.float64)
    rate = protocol['source_rate_hz']
    if values.shape != (7 * rate, 8) or not np.isfinite(values).all():
        raise ValueError('Complete finite original 7s fixed-eight trial required')
    if abs(cue_sample - 2 * rate) > 1 or protocol['target_rate_hz'] != 250:
        raise ValueError('Unexpected cue or target sample rate')
    if protocol['epoch_after_cue_s'] != [0.5, 2.5] or protocol['window_samples'] != 500:
        raise ValueError('This extractor implements the frozen 0.5-2.5s protocol only')
    # Use only the first sample as origin before the causal FIR's zero initial state.
    values = values - values[0]
    values = values - values.mean(axis=1, keepdims=True)
    up, down = 125, 256
    half = 10 * down
    fir = up * signal.firwin(2 * half + 1, 1 / down, window=('kaiser', 5))
    converted = signal.upfirdn(fir, values, up=up, down=down, axis=0)[:1750]
    conditioned = CausalEEGFilter().process(converted)
    start = round((cue_sample / rate + protocol['epoch_after_cue_s'][0]) * 250)
    stop = start + protocol['window_samples']
    bands = []
    for band in protocol['bands_hz']:
        sos = signal.butter(4, band, fs=250, btype='bandpass', output='sos')
        filtered = signal.sosfilt(sos, conditioned, axis=0)
        bands.append(filtered)
    return bands, start, stop


def trial_covariances(samples, cue_sample, protocol):
    bands, start, stop = _filtered_epoch(samples, cue_sample, protocol)
    return np.stack([normalized_covariance(band[start:stop], expected_samples=500)
                     for band in bands])


def trial_statistics(samples, cue_sample, protocol):
    """Same task covariance, plus unnormalized variances for the pre-cue ratio."""
    bands, start, stop = _filtered_epoch(samples, cue_sample, protocol)
    baseline_stop = round(cue_sample / protocol['source_rate_hz'] * 250)
    baseline_start = baseline_stop - 250
    if baseline_start < 0 or baseline_stop > start:
        raise ValueError('Complete causal -1..0s baseline required')
    covariance = np.stack([normalized_covariance(band[start:stop], expected_samples=500)
                           for band in bands])
    baseline_variance = np.stack([np.var(band[baseline_start:baseline_stop], axis=0, ddof=1)
                                  for band in bands])
    task_variance = np.stack([np.var(band[start:stop], axis=0, ddof=1) for band in bands])
    return covariance, baseline_variance, task_variance

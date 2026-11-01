"""Portable, NumPy-only SSVEP CCA baseline for PC and PYNQ ARM.

Input EEG uses shape ``(channels, samples)``.  This module intentionally does
not acquire hardware data or design the visual stimulus; those concerns must be
timestamped and validated separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


DEFAULT_FREQUENCIES = (7.3, 8.2, 9.3, 10.4, 11.5)


@dataclass(frozen=True)
class CCAResult:
    target_index: int
    frequency_hz: float
    score: float
    margin: float
    scores: np.ndarray
    accepted: bool


def reference_bank(
    frequencies: Iterable[float] = DEFAULT_FREQUENCIES,
    *,
    sample_rate_hz: float = 250.0,
    samples: int = 250,
    harmonics: int = 3,
) -> np.ndarray:
    """Return ``(targets, 2 * harmonics, samples)`` sinusoidal references."""
    if sample_rate_hz <= 0 or samples < 2 or harmonics < 1:
        raise ValueError("sample rate, samples and harmonics must be positive")
    t = np.arange(samples, dtype=np.float64) / float(sample_rate_hz)
    bank = []
    for frequency in frequencies:
        if frequency <= 0:
            raise ValueError("target frequencies must be positive")
        components = []
        for harmonic in range(1, harmonics + 1):
            phase = 2.0 * np.pi * harmonic * float(frequency) * t
            components.extend((np.sin(phase), np.cos(phase)))
        bank.append(components)
    return np.asarray(bank, dtype=np.float64)


def _inverse_sqrt(matrix: np.ndarray, regularization: float) -> np.ndarray:
    values, vectors = np.linalg.eigh(matrix)
    floor = max(float(values.max(initial=0.0)) * regularization, regularization)
    values = np.maximum(values, floor)
    return (vectors * (1.0 / np.sqrt(values))) @ vectors.T


def canonical_correlation(
    eeg: np.ndarray, reference: np.ndarray, *, regularization: float = 1e-6
) -> float:
    """Calculate the largest regularised canonical correlation."""
    x = np.asarray(eeg, dtype=np.float64).T
    y = np.asarray(reference, dtype=np.float64).T
    if x.ndim != 2 or y.ndim != 2 or x.shape[0] != y.shape[0]:
        raise ValueError("EEG and reference must be 2-D and share sample count")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("input contains NaN or infinity")
    x = x - x.mean(axis=0, keepdims=True)
    y = y - y.mean(axis=0, keepdims=True)
    scale = max(x.shape[0] - 1, 1)
    cxx = (x.T @ x) / scale
    cyy = (y.T @ y) / scale
    cxy = (x.T @ y) / scale
    whitened = _inverse_sqrt(cxx, regularization) @ cxy @ _inverse_sqrt(cyy, regularization)
    score = float(np.linalg.svd(whitened, compute_uv=False)[0])
    return float(np.clip(score, 0.0, 1.0))


class CachedCCA:
    """Same regularised CCA, with fixed references prepared once per stream."""
    def __init__(self, references: np.ndarray, regularization: float = 1e-6):
        bank = np.asarray(references, dtype=np.float64)
        if bank.ndim != 3 or min(bank.shape) < 1 or bank.shape[2] < 2:
            raise ValueError('Expected targets x components x samples')
        if not np.isfinite(bank).all() or regularization <= 0:
            raise ValueError('Expected finite references and positive regularization')
        self.regularization = regularization
        self.samples = bank.shape[2]
        self.scale = self.samples-1
        y = bank.transpose(0, 2, 1)
        self.centered = y - y.mean(axis=1, keepdims=True)
        self.whiteners = np.asarray([
            _inverse_sqrt(ref.T @ ref / self.scale, regularization)
            for ref in self.centered])

    def scores(self, eeg: np.ndarray) -> np.ndarray:
        x = np.asarray(eeg, dtype=np.float64).T
        if x.ndim != 2 or x.shape[0] != self.samples or not x.shape[1]:
            raise ValueError('EEG must match the cached reference sample count')
        if not np.isfinite(x).all():
            raise ValueError('EEG contains NaN or infinity')
        x = x - x.mean(axis=0, keepdims=True)
        whitening = _inverse_sqrt(x.T @ x / self.scale, self.regularization)
        cross = (x.T @ self.centered) / self.scale
        whitened = (whitening @ cross) @ self.whiteners
        return np.clip(np.linalg.svd(whitened, compute_uv=False)[:, 0], 0., 1.)

    def scores_rank2(self, eeg: np.ndarray) -> np.ndarray:
        """Exact 2-channel largest singular value via a batched 2x2 Gram matrix.

        Experimental engineering path: it changes only the small-matrix solver,
        not references, filtering, regularization, or decision thresholds.
        """
        x = np.asarray(eeg, dtype=np.float64).T
        if x.shape != (self.samples, 2) or not np.isfinite(x).all():
            raise ValueError('Expected finite two-channel EEG at cached sample length')
        x = x - x.mean(axis=0, keepdims=True)
        whitening = _inverse_sqrt(x.T @ x / self.scale, self.regularization)
        cross = (x.T @ self.centered) / self.scale
        whitened = (whitening @ cross) @ self.whiteners
        gram = whitened @ whitened.transpose(0, 2, 1)
        a, b, d = gram[:, 0, 0], gram[:, 0, 1], gram[:, 1, 1]
        largest = (a + d + np.hypot(a - d, 2.0 * b)) * 0.5
        return np.clip(np.sqrt(np.maximum(largest, 0.)), 0., 1.)


def classify(
    eeg: np.ndarray,
    *,
    frequencies: Iterable[float] = DEFAULT_FREQUENCIES,
    sample_rate_hz: float = 250.0,
    harmonics: int = 3,
    minimum_score: float = 0.0,
    minimum_margin: float = 0.0,
) -> CCAResult:
    """Classify one window and optionally reject low-confidence decisions.

    Rejection thresholds default to zero because they must be chosen using
    calibration/validation trials, never guessed from the test session.
    """
    signal = np.asarray(eeg, dtype=np.float64)
    if signal.ndim != 2 or signal.shape[0] < 1 or signal.shape[1] < 2:
        raise ValueError("expected EEG with shape (channels, samples)")
    targets = tuple(float(value) for value in frequencies)
    references = reference_bank(
        targets,
        sample_rate_hz=sample_rate_hz,
        samples=signal.shape[1],
        harmonics=harmonics,
    )
    scores = np.asarray(
        [canonical_correlation(signal, reference) for reference in references],
        dtype=np.float64,
    )
    order = np.argsort(scores)
    winner = int(order[-1])
    runner_up = float(scores[order[-2]]) if len(scores) > 1 else 0.0
    margin = float(scores[winner] - runner_up)
    accepted = bool(scores[winner] >= minimum_score and margin >= minimum_margin)
    return CCAResult(
        target_index=winner,
        frequency_hz=targets[winner],
        score=float(scores[winner]),
        margin=margin,
        scores=scores,
        accepted=accepted,
    )

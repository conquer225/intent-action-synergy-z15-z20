"""Deterministic software checks for the portable CCA implementation."""

from __future__ import annotations

import numpy as np

from ssvep_core import DEFAULT_FREQUENCIES, classify


def synthetic_eeg(frequency_hz: float, seed: int) -> np.ndarray:
    sample_rate_hz = 250.0
    samples = 250
    t = np.arange(samples) / sample_rate_hz
    rng = np.random.default_rng(seed)
    channels = []
    for phase in np.linspace(0.0, 0.8, 8):
        channels.append(
            np.sin(2 * np.pi * frequency_hz * t + phase)
            + 0.35 * np.sin(4 * np.pi * frequency_hz * t + phase / 2)
            + rng.normal(0.0, 0.25, samples)
        )
    return np.asarray(channels)


def main() -> None:
    for index, frequency in enumerate(DEFAULT_FREQUENCIES):
        result = classify(synthetic_eeg(frequency, 20260922 + index))
        if result.target_index != index:
            raise AssertionError(
                f"expected {frequency} Hz, got {result.frequency_hz} Hz: {result.scores}"
            )
        print(
            f"PASS target={index + 1} frequency={frequency:.1f}Hz "
            f"score={result.score:.4f} margin={result.margin:.4f}"
        )
    print("SSVEP_CCA_SYNTHETIC_SELFTEST_OK")


if __name__ == "__main__":
    main()

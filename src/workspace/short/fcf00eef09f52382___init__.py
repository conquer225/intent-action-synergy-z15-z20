"""Robustness experiments for the GuardianLoop low-channel EEG pipeline."""

from .corruptions import (
    CorruptionResult,
    CorruptionSpec,
    apply_feature_corruption,
    sample_training_corruption,
)

__all__ = [
    "CorruptionResult",
    "CorruptionSpec",
    "apply_feature_corruption",
    "sample_training_corruption",
]

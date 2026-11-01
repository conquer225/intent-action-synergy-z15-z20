"""Audit corruption magnitudes against the cached SEED-VIG DE features."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from corruptions import CorruptionSpec, apply_feature_corruption


SOURCE_CHANNELS = (
    "FT7", "FT8", "T7", "T8", "TP7", "TP8", "CP1", "CP2", "P1",
    "PZ", "P2", "PO3", "POZ", "PO4", "O1", "OZ", "O2",
)
TARGET_CHANNELS = ("FT7", "FT8", "CP1", "CP2", "P1", "P2", "O1", "O2")
KINDS = (
    "dropout", "flatline", "broadband_noise", "mains_noise", "drift", "burst",
    "channel_swap",
)
SEVERITIES = (0.33, 0.66, 1.0)


def load_features(cache: Path) -> np.ndarray:
    columns = []
    for channel in TARGET_CHANNELS:
        source_index = SOURCE_CHANNELS.index(channel)
        columns.extend(range(source_index * 5, source_index * 5 + 5))
    recordings = []
    for path in sorted(cache.glob("*.npz")):
        with np.load(path, allow_pickle=False) as item:
            recordings.append(np.asarray(item["features"][:, columns], dtype=np.float64))
    if not recordings:
        raise FileNotFoundError(f"no cached recordings found under {cache}")
    return np.concatenate(recordings).reshape(-1, len(TARGET_CHANNELS), 5)


def digest(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).view(np.uint8)).hexdigest()


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=here.parent / "cache_all17")
    parser.add_argument("--output", type=Path, default=here / "corruption_protocol_v1_audit.json")
    args = parser.parse_args()

    source = load_features(args.cache)
    # Audit a long, fixed episode so every severity is compared on identical data.
    start = min(500, len(source) // 10)
    length = min(4000, len(source) - start)
    rows = []
    for kind in KINDS:
        for severity in SEVERITIES:
            channels = (1, 6) if kind != "channel_swap" else (0, 1)
            result = apply_feature_corruption(
                source,
                CorruptionSpec(kind, severity, channels, start, length),
                seed=20260919,
            )
            delta = np.abs(result.features - source)
            changed = result.corruption_mask
            expanded_mask = np.repeat(changed[:, :, None], source.shape[2], axis=2)
            changed_delta = delta[expanded_mask]
            rows.append({
                **result.metadata,
                "finite": bool(np.all(np.isfinite(result.features))),
                "changed_channel_windows": int(np.count_nonzero(changed)),
                "changed_fraction": float(np.mean(changed)),
                "global_mean_abs_feature_delta": float(np.mean(delta)),
                "changed_mean_abs_feature_delta": float(np.mean(changed_delta)),
                "changed_p95_abs_feature_delta": float(np.quantile(changed_delta, 0.95)),
                "max_abs_feature_delta": float(np.max(delta)),
                "mean_quality": float(np.mean(result.quality)),
                "output_sha256": digest(result.features),
            })

    soft_kinds = ("broadband_noise", "mains_noise", "drift", "burst")
    monotonic_checks = {}
    for kind in soft_kinds:
        effects = [
            row["global_mean_abs_feature_delta"] for row in rows if row["kind"] == kind
        ]
        monotonic_checks[kind] = bool(all(
            later > earlier for earlier, later in zip(effects, effects[1:])
        ))

    payload = {
        "protocol_version": "guardianloop-structured-feature-corruption-v1",
        "domain": "SEED-VIG differential-entropy features",
        "feature_shape": list(source.shape),
        "channels": list(TARGET_CHANNELS),
        "bands": ["delta", "theta", "alpha", "beta", "gamma"],
        "source_sha256": digest(source),
        "episode": {"start": start, "length": length},
        "checks": {
            "all_finite": all(row["finite"] for row in rows),
            "soft_severity_effect_is_strictly_increasing": monotonic_checks,
        },
        "results": rows,
        "notes": [
            "Microvolt thresholds are not applied directly to DE features.",
            "All magnitudes except dropout/flatline/swap use per-recording robust scale.",
            "channel_swap is evaluation-only because electrically valid signals may have wrong identities.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "feature_shape": payload["feature_shape"],
        "scenarios": len(rows),
        "all_finite": all(row["finite"] for row in rows),
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# SQI v2 clean-aware calibration and feature ablation

Run date: 2026-09-20

## Frozen hypothesis and success criteria

Explicit clean examples, an actionable (rather than purely synthetic
electrical) quality target, and training-only calibration should reduce the
clean false-bad rate below 15% while preserving or improving robustness.

Failure was defined as either:

- clean false-bad rate at least 15%; or
- no predicted-gating variant with participant-stable robustness benefit and
  no more than 0.01 clean CCC loss.

## Changes from v1

- Added untouched clean training examples with quality target 1.
- Calibrated each fold's SQI output using only the 10th percentile of clean
  training-participant predictions.
- Treated the weak DE-domain mains approximation as non-actionable because v1
  Oracle gating showed that removing those channels was harmful.
- Compared two declared SQI feature sets:
  - five DE bands only;
  - DE bands plus absolute first differences, causal five-window standard
    deviations, and absolute spatial-median residuals.
- Kept the fatigue model, LOSO splits, 217 test conditions, and seeds fixed.

## Primary calibration endpoint

| SQI feature set | Clean quality MAE | Clean false-bad rate |
|---|---:|---:|
| DE bands | 0.0249 | 7.30% |
| Full SQI | 0.0185 | 6.34% |

Both variants pass the preregistered `<15%` endpoint. V1 was approximately
51%, so the clean-aware correction is material.

## Untouched clean fatigue performance

| Method | PCC | RMSE | CCC | Macro-F1 |
|---|---:|---:|---:|---:|
| Predicted gate v1 | 0.6818 | 0.1991 | 0.6412 | 0.5887 |
| SQI v2, DE bands | 0.6758 | 0.1993 | 0.6518 | 0.6008 |
| SQI v2, full | 0.6833 | 0.1970 | 0.6581 | 0.6047 |

The full SQI feature set is retained. Its clean CCC is 0.0168 above v1 in the
pooled result, although participant-level clean improvement is heterogeneous
and is not claimed as confirmatory.

## Four-channel, high-severity pooled CCC gains

Full SQI v2 relative to clean-trained HGB:

| Corruption | CCC gain |
|---|---:|
| Dropout | +0.0651 |
| Flatline | +0.0523 |
| Broadband noise | +0.0323 |
| Drift | +0.0492 |
| Burst | +0.0467 |
| Mains approximation | +0.0221 |

Full SQI v2 relative to predicted-gate v1:

| Corruption | CCC gain |
|---|---:|
| Dropout | +0.0407 |
| Flatline | +0.0407 |
| Broadband noise | +0.0064 |
| Drift | +0.0141 |
| Burst | +0.0205 |
| Mains approximation | +0.0343 |

## Participant-level evidence

For high-severity, four-channel corruption after averaging seeds within each
participant:

- Dropout vs clean HGB: mean CCC gain `+0.0672`, 95% participant-bootstrap CI
  `[+0.0412, +0.0963]`, 18/21 positive. Holm-adjusted p-value across the 12
  v2 comparisons is `0.00040`.
- Flatline vs v1 predicted gating: mean CCC gain `+0.0306`, 95% CI
  `[+0.0017, +0.0569]`, 18/21 positive. Holm-adjusted p-value `0.0441`.
- Other mean gains are positive except none, but their multiplicity-corrected
  participant tests do not cross 0.05. They remain exploratory.

## Decision

SQI v2 passes the predefined calibration criterion and provides a defensible
small-model predicted-gating baseline. The full feature set is retained because
it has lower clean SQI error and stronger pooled behavior than DE bands alone.

This is still synthetic feature-domain evidence. Do not tune the corruption
generator further against these results. The next discriminating step is a
small unlabeled Cyton transfer dataset containing clean contact, hair-obstructed
contact, loose electrode, movement/burst, brief disconnect, and recovery. It
can validate SQI/contact-failure transfer but cannot validate fatigue accuracy
without a separate vigilance-labeling protocol.

## Evidence

- `results/quality_aware_hgb_v2/config.json`
- `results/quality_aware_hgb_v2/split_manifest.json`
- `results/quality_aware_hgb_v2/fold_metrics.csv`
- `results/quality_aware_hgb_v2/condition_metrics.csv`
- `results/quality_aware_hgb_v2/quality_metrics.csv`
- `results/quality_aware_hgb_v2/predictions.npz`
- `results/quality_aware_hgb_v2/summary.json`
- `../../output/jupyter-notebook/guardianloop-sqi-v2-ablation.ipynb`

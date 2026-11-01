# HGB structured-corruption baseline v1

Run date: 2026-09-20

## Frozen protocol

- Dataset cache: 23 SEED-VIG recordings from 21 participant groups.
- Split: strict participant-grouped LOSO.
- Layout: `FT7, FT8, CP1, CP2, P1, P2, O1, O2`.
- Input: five DE bands per channel.
- Calibration: first 15 windows (120 s), excluded from scoring.
- Model: clean-only HistGradientBoostingRegressor; fold model and class thresholds are frozen before test corruption.
- Test corruption: held-out post-calibration DE, before causal EMA.
- Matrix: 7 corruption types x 3 severity levels x 3 deterministic seeds.
- This v1 run corrupts exactly two channels. Severity increases episode duration from 10% to 25% to 40%, and also increases perturbation magnitude where the generator supports it.

## Clean baseline

| PCC | RMSE | CCC | Macro-F1 |
|---:|---:|---:|---:|
| 0.6586 | 0.2042 | 0.6330 | 0.5876 |

## Largest aggregate losses

| Condition | PCC | RMSE | CCC | CCC change |
|---|---:|---:|---:|---:|
| Broadband noise, high | 0.5965 | 0.2186 | 0.5661 | -0.0669 |
| Dropout, high | 0.6109 | 0.2168 | 0.5672 | -0.0658 |
| Flatline, high | 0.6168 | 0.2136 | 0.5877 | -0.0453 |
| Flatline, medium | 0.6165 | 0.2143 | 0.5901 | -0.0429 |
| Drift, high | 0.6200 | 0.2131 | 0.5934 | -0.0396 |

The hypothesis is partially supported. Strong broadband noise, dropout,
flatline, and drift reduce aggregate performance, but the average loss under
two-channel episodic corruption is modest. Low-severity mains perturbation and
channel swap do not reliably degrade aggregate performance in this protocol.

The participant-level Wilcoxon audit is exploratory. After Holm correction
across 21 RMSE comparisons, low and medium flatline conditions remain below
0.05; other conditions do not. This is not evidence that low flatline is more
damaging than high flatline. The non-monotonic significance reflects
participant heterogeneity and limited sample size; effect magnitudes and the
next channel-count sweep are more informative.

## What this does and does not establish

This run establishes a reproducible clean baseline and identifies candidate
failure modes. It does not yet establish the paper's proposed contribution.
The corruptions are synthetic feature-domain approximations, not real Cyton
voltage artifacts. The run covers two affected channels only, does not test a
quality-aware model, and does not evaluate ViFormerNet.

## Locked next experiment — completed

1. Sweep 1, 2, 3, and 4 affected channels while preserving the clean test.
2. Report participant-level PCC, RMSE, CCC, Macro-F1, and robustness AUC.
3. Train a quality-aware channel-gating model only after the failure boundary
   is known.
4. Compare clean HGB, corrupted HGB, and quality-aware HGB under the identical
   split manifest.
5. Validate the synthetic ranking with a small, labeled Cyton artifact set.

The 1/2/3/4-channel sweep is now complete. See `CHANNEL_COUNT_RESULTS.md`.

## Reproduction

```powershell
python .\viformer_z15\robustness\evaluate_hgb_robustness.py `
  --output-dir .\viformer_z15\robustness\results\hgb_symmetric_v1
```

Evidence bundle:

- `results/hgb_symmetric_v1/config.json`
- `results/hgb_symmetric_v1/split_manifest.json`
- `results/hgb_symmetric_v1/fold_metrics.csv`
- `results/hgb_symmetric_v1/condition_metrics.csv`
- `results/hgb_symmetric_v1/predictions.npz`
- `results/hgb_symmetric_v1/summary.json`
- `../../output/jupyter-notebook/guardianloop-hgb-corruption-baseline.ipynb`

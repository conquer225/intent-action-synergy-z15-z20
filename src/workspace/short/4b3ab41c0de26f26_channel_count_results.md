# HGB bad-channel count sweep v1

Run date: 2026-09-20

## Question and decision rule

Hypothesis: PCC and CCC decrease and RMSE increases as affected channels rise
from one to four, especially for broadband noise, dropout, and flatline.

Falsification condition: most corruption families lack a consistent dose
trend or participant-level effect directions are highly unstable.

## Frozen protocol

- 23 SEED-VIG recordings, 21 participant groups, strict LOSO.
- Symmetric layout: `FT7, FT8, CP1, CP2, P1, P2, O1, O2`.
- Clean-only HGB training and threshold fitting.
- First 120 s used for unlabeled calibration and excluded from scoring.
- Held-out feature corruption after calibration and before causal EMA.
- Six corruption families, three severities, 1/2/3/4 affected channels, three seeds.
- Channel subsets are nested within each recording/severity/seed.
- `channel_swap` is excluded from this sweep and retained as a separate identity-error test.

The matrix contains 217 conditions including clean and stores 20,010 held-out
windows per condition.

## Clean reference

| PCC | RMSE | CCC | Macro-F1 |
|---:|---:|---:|---:|
| 0.6586 | 0.2042 | 0.6330 | 0.5876 |

## Four-channel, high-severity pooled results

| Corruption | PCC | RMSE | CCC | CCC change |
|---|---:|---:|---:|---:|
| Dropout | 0.5795 | 0.2272 | 0.5249 | -0.1081 |
| Flatline | 0.5522 | 0.2294 | 0.5255 | -0.1075 |
| Broadband noise | 0.5843 | 0.2207 | 0.5467 | -0.0863 |
| Drift | 0.6030 | 0.2179 | 0.5768 | -0.0562 |
| Burst | 0.6211 | 0.2130 | 0.5947 | -0.0383 |
| Mains approximation | 0.6595 | 0.2035 | 0.6241 | -0.0089 |

## Participant-level four-channel effects

The following are mean within-participant changes after averaging the three
seeds. Confidence intervals are 10,000-repeat participant bootstrap intervals.

| Corruption | Mean CCC change | 95% CI | Mean RMSE change | 95% CI |
|---|---:|---:|---:|---:|
| Dropout | -0.1126 | [-0.1567, -0.0734] | +0.0206 | [+0.0071, +0.0365] |
| Flatline | -0.0826 | [-0.1203, -0.0481] | +0.0222 | [+0.0097, +0.0358] |
| Broadband noise | -0.0785 | [-0.1059, -0.0514] | +0.0142 | [+0.0041, +0.0246] |
| Drift | -0.0469 | [-0.0713, -0.0240] | +0.0123 | [+0.0045, +0.0202] |
| Burst | -0.0321 | [-0.0452, -0.0188] | +0.0086 | [+0.0036, +0.0136] |
| Mains approximation | -0.0142 | [-0.0271, -0.0036] | -0.0009 | [-0.0037, +0.0017] |

## Dose-trend audit

At high severity, the participant-level CCC slope over 0–4 affected channels
is negative for 19/21 participants under broadband noise, 20/21 under dropout,
18/21 under flatline, 17/21 under drift, and 19/21 under burst. All six CCC
slopes remain significant after Holm correction across the 18
family/severity comparisons; the mains effect is weak and is not supported by
RMSE.

The high-severity RMSE slopes for burst, drift, and flatline remain below 0.05
after Holm correction. Broadband-noise and dropout RMSE slope tests are close
but above 0.05 after correction, even though their CCC effects and bootstrap
intervals show clear degradation. This metric disagreement must be retained,
not hidden.

## Decision

The preregistered dose hypothesis is supported for the main contact-failure
families. The next experiment should be a quality-aware channel-gating HGB
baseline under the identical manifest. The minimum comparison is:

1. clean-trained HGB;
2. HGB with random masking augmentation;
3. HGB with full structured-corruption augmentation;
4. oracle quality masking/gating;
5. predicted-quality gating.

ViFormerNet should remain deferred until this small-model experiment measures
the available robustness headroom. The feature-domain mains approximation is
too weak to support a headline physical-interference claim; real Cyton
recordings are still needed for external realism validation.

The first quality-aware HGB ablation is now complete. See
`QUALITY_AWARE_RESULTS.md`.

## Reproduction and evidence

```powershell
python .\viformer_z15\robustness\evaluate_hgb_channel_count_sweep.py `
  --output-dir .\viformer_z15\robustness\results\hgb_channel_count_sweep_v1
```

- `results/hgb_channel_count_sweep_v1/config.json`
- `results/hgb_channel_count_sweep_v1/split_manifest.json`
- `results/hgb_channel_count_sweep_v1/fold_metrics.csv`
- `results/hgb_channel_count_sweep_v1/condition_metrics.csv`
- `results/hgb_channel_count_sweep_v1/predictions.npz`
- `results/hgb_channel_count_sweep_v1/summary.json`
- `../../output/jupyter-notebook/guardianloop-hgb-channel-count-sweep.ipynb`

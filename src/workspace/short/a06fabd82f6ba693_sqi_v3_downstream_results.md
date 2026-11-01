# SQI-v3 downstream vigilance results

## Frozen evaluation status

This report records the frozen public-data experiment. It uses 21 SEED-VIG
participants, participant-held-out LOSO evaluation, three corruption severities
(0.25, 0.50, 0.75), three random seeds, and six corruption families. All SQI
thresholds and model parameters are learned without the held-out participant.
Statistics use participants as independent units; windows are never treated as
independent replicates.

The R1-R3 wet-gauze Cyton recordings were not used as confirmatory evidence.
Future R4+ placements remain untouched.

## Main result

SQI-v3 is a strong synthetic-corruption detector, but the current quality-gating
mechanism does **not** improve vigilance regression beyond corruption-augmented
training without gating.

Across all six corruption families, mean corrupted-episode RMSE was:

| Method | Mean episode RMSE |
|---|---:|
| Clean-only fatigue model | 0.1891 |
| Corruption augmentation, no gate | **0.1719** |
| Oracle hard gate | 0.1718 |
| SQI-v3 hard gate | 0.1725 |
| Oracle soft gate | 0.1720 |
| SQI-v3 soft gate | 0.1775 |

Corruption augmentation reduced episode RMSE by 0.0171 relative to clean-only
training (participant bootstrap 95% CI 0.0082 to 0.0262; two-sided Wilcoxon
`p=0.00118`). This corresponds to an average relative reduction of about 9.1%.

By contrast, SQI-v3 soft gating was 0.0056 RMSE worse than augmentation alone;
the paired confidence interval crossed zero (-0.0193 to 0.0073) and the
difference was not significant (`p=0.633`). Its full-recording RMSE and CCC also
did not improve (`p=0.320` and `p=0.288`, respectively).

The clean-data comparison showed no statistically supported degradation, but
also no benefit: SQI-v3 soft gating changed clean RMSE by -0.0013 in the
improvement convention (95% CI -0.0034 to 0.0006; `p=0.257`) and clean CCC by
-0.0037 (95% CI -0.0097 to 0.0018; `p=0.338`).

## Per-corruption primary endpoint

The primary endpoint was participant-level corrupted-episode RMSE for SQI-v3
soft gating versus corruption augmentation without gating. Positive differences
favour SQI-v3.

| Corruption | Augmented no gate | SQI-v3 soft | Mean improvement | 95% CI | Holm-adjusted p |
|---|---:|---:|---:|---:|---:|
| Flatline | 0.1749 | 0.1849 | -0.0100 | [-0.0241, 0.0047] | 1.000 |
| Broadband noise | 0.1727 | 0.1744 | -0.0016 | [-0.0192, 0.0152] | 1.000 |
| Mains noise | 0.1648 | 0.1757 | -0.0108 | [-0.0289, 0.0041] | 1.000 |
| Drift | 0.1726 | 0.1837 | -0.0111 | [-0.0276, 0.0026] | 1.000 |
| Burst | 0.1723 | 0.1671 | +0.0052 | [-0.0148, 0.0232] | 1.000 |
| Cable motion | 0.1742 | 0.1792 | -0.0050 | [-0.0203, 0.0119] | 1.000 |

No corruption-specific downstream gain survives participant-level inference or
Holm correction.

## Why detection success did not become regression gain

The failure is not explained mainly by an inaccurate SQI classifier. Oracle hard
gating, which receives the true synthetic corruption mask, improved episode RMSE
by only 0.00012 versus augmentation alone (95% CI -0.00933 to 0.00885;
`p=0.412`). SQI-v3 hard gating similarly showed no gain (-0.00052; 95% CI
-0.0111 to 0.00890; `p=0.733`). Therefore the present gating representation has
little usable headroom even with perfect quality labels.

The likely mechanism is that multiplying or replacing channel features by a
quality score removes information in a way the downstream HGB regressor cannot
reconstruct. Synthetic corruption augmentation already teaches the regressor to
discount unreliable feature patterns while retaining useful residual signal.
Soft probabilities also need not be calibrated measures of signal fidelity, so
using `1 - P(bad)` as a direct amplitude weight is not theoretically guaranteed.

## What is supported

1. The raw-transient-aware SQI classifier has high synthetic-corruption balanced
   accuracy (91.2%-98.5% across the six families) with 2.02% clean false-bad rate.
2. Relative to the DE-only SQI baseline, participant-level gains are supported
   for drift (+40.7 percentage points) and burst (+3.9 points), but not cable
   motion (+0.94 points; Holm `p=0.175`).
3. Corruption-augmented fatigue training provides a statistically supported
   robustness gain over clean-only training.
4. The current hard/soft quality-gating designs add no supported downstream gain
   beyond augmentation.

## What must not yet be claimed

- Do not claim real-head or real-Cyton corruption generalization from synthetic
  SEED-VIG experiments.
- Do not claim that SQI-v3 improves fatigue-estimation accuracy through gating.
- Do not claim cable-motion superiority; its detector gain over the DE-only
  baseline was not significant after correction.
- Do not tune features or thresholds on the future R4+ confirmation placements.

## Recommended frozen system for the next hardware phase

Use the corruption-augmented fatigue model as the inference baseline. Run SQI-v3
in parallel as a quality monitor and warning signal, not as a feature gate. Freeze
the current SQI-v3 feature set and thresholds before R4+ collection.

The next experiment is the preregistered R4+ hardware confirmation: at least
three independent placements, preferably on another day, with 16 s static,
40 s controlled cable motion, 24 s recovery, open-contact, and restored-contact
segments. Report placement-level confidence intervals and retain raw hashes,
packet-loss logs, action timestamps, and device configuration.

Only after R4+ should a new gating architecture be explored. The most defensible
next candidate is channel masking/attention with explicit missingness indicators
and training-time channel dropout, not direct multiplication by uncalibrated
bad-probabilities. That work is a new exploratory version and must not overwrite
the frozen SQI-v3 result.

## Reproducibility files

- `run_raw_sqi_v3_downstream_full.py`: executes the 3 x 3 frozen runs.
- `evaluate_raw_sqi_v3_downstream.py`: participant-held-out downstream protocol.
- `analyze_raw_sqi_v3_downstream.py`: participant bootstrap, Wilcoxon tests, and
  Holm correction.
- `results/raw_sqi_v3_downstream_full_frozen/participant_statistics.json`:
  machine-readable statistical output.
- `results/raw_sqi_v3_downstream_full_frozen/participant_paired_values.csv`:
  participant-level paired values.
- `results/raw_sqi_v3_downstream_full_frozen/figures/`: paper-ready PNG and PDF.

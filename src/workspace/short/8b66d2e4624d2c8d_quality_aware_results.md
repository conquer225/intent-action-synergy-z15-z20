# Quality-aware HGB ablation v1

Run date: 2026-09-20

## Preregistered decision rule

- If Oracle gating fails, stop the gating direction.
- If Oracle succeeds but predicted gating fails, retain the gating architecture
  and improve the signal-quality estimator.
- Preserve clean evaluation and every corruption condition; do not tune against
  the held-out participant.

## Compared methods

1. `clean_hgb`: clean-only HGB.
2. `random_mask_aug`: HGB trained with random channel dropout.
3. `structured_aug`: HGB trained with six structured corruption families.
4. `oracle_gate`: structured training plus generator-provided channel quality.
5. `predicted_gate`: the same gated fatigue model using a fold-trained SQI regressor.

The SQI regressor uses five DE bands, absolute first differences, causal
five-window standard deviations, and absolute residuals from the spatial
channel median. Gating occurs before causal EMA; the gated model also receives
eight smoothed channel-quality values.

## Untouched clean results

| Method | PCC | RMSE | CCC | Macro-F1 |
|---|---:|---:|---:|---:|
| Clean HGB | 0.6586 | 0.2042 | 0.6330 | 0.5876 |
| Random-mask augmentation | 0.6691 | 0.2010 | 0.6444 | 0.5943 |
| Structured augmentation | 0.6707 | 0.1998 | 0.6343 | 0.5995 |
| Oracle gate | 0.6776 | 0.1987 | 0.6523 | 0.6056 |
| Predicted gate | 0.6818 | 0.1991 | 0.6412 | 0.5887 |

Pooled clean metrics do not show a clean-performance penalty. Participant-level
clean gains are smaller and heterogeneous; clean improvement is not treated as
the main claim.

## Four-channel, high-severity pooled CCC gains

Positive values are improvements over `clean_hgb` under the identical
corrupted test condition.

| Corruption | Random mask | Structured aug. | Oracle gate | Predicted gate |
|---|---:|---:|---:|---:|
| Dropout | +0.0593 | +0.0131 | +0.0640 | +0.0244 |
| Flatline | +0.0099 | +0.0228 | +0.0565 | +0.0117 |
| Broadband noise | -0.0090 | +0.0174 | +0.0542 | +0.0259 |
| Drift | -0.0003 | +0.0215 | +0.0180 | +0.0351 |
| Burst | +0.0050 | +0.0088 | +0.0443 | +0.0262 |
| Mains approximation | +0.0122 | -0.0070 | -0.0274 | -0.0122 |

The Oracle result demonstrates useful robustness headroom for the main contact
failure families. The weak feature-domain mains perturbation should not be
gated with the current synthetic quality target: removing channels is worse
than tolerating this perturbation.

## Participant-level paired evidence

Seeds are averaged inside participant. Confidence intervals use 10,000
participant bootstrap repetitions. Holm correction covers 24 method/family
comparisons.

- Oracle/dropout CCC gain: `+0.0741`, 95% CI `[+0.0470, +0.1026]`, 19/21
  participants positive, Holm-adjusted `p=0.00022`.
- Oracle/flatline RMSE gain: `+0.0179`, 95% CI `[+0.0089, +0.0265]`, 17/21
  participants positive, Holm-adjusted `p=0.0102`.
- Oracle broadband-noise and burst mean gains are positive, but their
  multiplicity-corrected CCC tests are not below 0.05.
- Predicted-gate CCC confidence intervals cross zero for every high-severity
  four-channel family. Its dropout RMSE gain is the only predicted-gate result
  below 0.05 after correction.

## SQI diagnosis

At the diagnostic quality threshold of 0.90, the fold-trained SQI regressor has
a clean false-bad rate of about 51%. Recall on strong synthetic corruption is
very high, but precision and calibration are poor. Continuous soft gating can
still improve pooled fatigue metrics, but the current SQI is not sufficient for
a strong participant-independent robustness claim.

## Decision

The gating architecture passes the Oracle test, so the direction remains
viable. The current predicted-quality method does not yet pass the stronger
participant-level test. Freeze this run as v1 and proceed with:

1. clean-aware SQI training with explicit clean recording examples;
2. training-only probability/quality calibration;
3. SQI feature-group ablations;
4. a policy that gates severe contact failures but leaves weak mains-like
   perturbations untouched;
5. rerunning the identical split and corruption manifest.

Do not move to ViFormerNet yet. The current bottleneck is quality estimation,
not fatigue-model capacity.

The clean-aware SQI v2 follow-up is now complete. See `SQI_V2_RESULTS.md`.

## Evidence

- `results/quality_aware_hgb_v1/config.json`
- `results/quality_aware_hgb_v1/split_manifest.json`
- `results/quality_aware_hgb_v1/fold_metrics.csv`
- `results/quality_aware_hgb_v1/condition_metrics.csv`
- `results/quality_aware_hgb_v1/quality_metrics.csv`
- `results/quality_aware_hgb_v1/predictions.npz`
- `results/quality_aware_hgb_v1/summary.json`
- `../../output/jupyter-notebook/guardianloop-quality-aware-hgb.ipynb`

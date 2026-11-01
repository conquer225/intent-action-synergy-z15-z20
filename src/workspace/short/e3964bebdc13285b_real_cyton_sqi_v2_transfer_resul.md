# Frozen SQI v2: Stage-A Cyton bench transfer result

## Decision

The frozen SQI v2 passed this first real-hardware transfer check. It detected
the deliberately opened or moved channel while leaving nearly all unaffected
channel-windows unflagged. This supports proceeding to a small, repeated
Stage-B validation; it does **not** yet establish physiological EEG quality or
fatigue-estimation accuracy.

## Frozen protocol

- SQI estimator: final HistGradientBoosting model trained on all public
  SEED-VIG recordings plus the already-defined synthetic corruptions.
- Real Cyton data used for fitting or threshold selection: **no**.
- Frequency features: causal five-band DE (1-4, 4-8, 8-14, 14-31, 31-50 Hz).
- Window: non-overlapping 8 s at 250 Hz.
- Calibration: first 15 windows (120 s) of B1-R, shared by every Stage-A file.
- Fixed bad-channel rule: SQI < 0.90.
- Ambiguous B4 recovery window was excluded from the confusion-matrix result.

## Main result

Across conditions with unambiguous bench labels:

- True positive channel-windows: 29
- False negative channel-windows: 4
- True negative channel-windows: 342
- False positive channel-windows: 1
- Sensitivity: 87.88%
- Specificity: 99.71%
- Balanced accuracy: 93.79%

All four directional checks passed:

1. B2 CH1 scored below the unaffected channels.
2. B3 CH1-CH3 scored below the unaffected channels.
3. B4 moving CH4 scored below its pre-motion value.
4. B5 had a lower bad-window fraction than B3.

The most interpretable channel medians were:

- B1-R stable reference: all channels 1.00.
- B2 single open: CH1 0.50; CH2-CH8 1.00.
- B3 three open: CH1 0.58, CH2 0.60, CH3 0.70; CH4-CH8 1.00.
- B4 motion: CH4 0.74; the other channels 1.00.
- B5 restored: all channels 1.00.

## Important caveats

- The observations are 8 s channel-windows from one setup, not independent
  human subjects. The 93.79% figure must not be presented as population-level
  accuracy.
- B4 contains only one pre-motion and one immediate recovery window. CH8 was a
  false positive before motion, and CH4 remained low in the immediate recovery
  window. The longer B5 recording then returned all channels to 1.00.
- Wet-gauze common-contact data verify acquisition/SQI behavior only. They are
  not EEG and cannot validate fatigue, emotion, or BCI decoding.
- The calibration currently comes from the same bench arrangement. Stage B
  should repeat the protocol on separate placements/days and report
  placement-grouped confidence intervals.

## Next experiment (Stage B)

Repeat B1-R/B2/B3/B4/B5 on at least three independent re-placements without
changing the model or threshold. Randomize the order of B2-B4, retain B1-R at
the start and B5 at the end, and save exact action timestamps. The primary
endpoints should be affected-channel sensitivity and unaffected-channel
specificity grouped by placement, with bootstrap confidence intervals over
placements rather than treating windows as independent replicates.

## Reproducible artifacts

- Analysis script: `evaluate_real_cyton_sqi_transfer.py`
- Full configuration and SHA-256 hashes: `results/real_cyton_sqi_v2_transfer/config.json`
- Window-level scores: `results/real_cyton_sqi_v2_transfer/window_channel_scores.csv`
- Channel summaries: `results/real_cyton_sqi_v2_transfer/channel_summary.csv`
- Figure: `results/real_cyton_sqi_v2_transfer/channel_condition_heatmap.png`
- Fitted public-data model: `results/real_cyton_sqi_v2_transfer/sqi_v2_public_final.joblib`
- B1-R deployment calibration: `results/real_cyton_sqi_v2_transfer/b1r_de_calibration.npz`

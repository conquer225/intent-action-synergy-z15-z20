# SQI v3 preregistration: raw-transient-aware quality gating

## Status and data roles

- R1-R3 Cyton wet-gauze recordings: exploratory/development evidence only.
- SEED-VIG participants: public-data training and participant-grouped LOSO.
- Synthetic corruptions: generated inside each training fold only.
- Future Cyton placements R4+: untouched confirmatory hardware test.
- No threshold or feature choice may be selected using R4+.

## Hypothesis

Adding causal raw-domain transient and spectral descriptors to the existing
DE-domain SQI will improve cable-motion sensitivity without reducing known-
clean specificity below 95% or materially degrading clean fatigue estimation.

## Falsification criteria

The idea is rejected if any of the following occurs:

1. future placement-level cable-motion sensitivity remains below 80%;
2. future known-clean specificity falls below 95%;
3. public clean false-bad rate exceeds 15%;
4. quality gating materially worsens clean fatigue RMSE or CCC relative to
   frozen SQI v2 under identical LOSO splits.

## Causal feature families

Each 8 s channel-window may use only present and past samples:

1. existing five-band DE and its causal temporal/spatial diagnostics;
2. log robust amplitude (MAD), 95th-percentile, and maximum absolute amplitude;
3. log derivative MAD, maximum absolute derivative, and transient count;
4. flat-step and rail fractions;
5. 1-4 Hz, 31-50 Hz, and 48-50 Hz power ratios;
6. raw spatial-median residual;
7. packet continuity as a separate transport flag, not an EEG channel feature.

All normalization statistics are fitted from training participants or from the
declared unlabeled 120 s deployment calibration. No future test session may be
used to fit normalization.

## Fixed comparisons

1. frozen SQI v2;
2. fixed handcrafted raw-quality rules;
3. SQI v3 with DE plus raw features;
4. SQI v3 without derivative/transient features;
5. SQI v3 without spectral-ratio features;
6. oracle corruption mask for headroom where synthetic truth is available.

## Primary metrics

- Quality detection: affected-channel sensitivity, unaffected-channel
  specificity, balanced accuracy, and clean false-bad rate.
- Fatigue model: participant-level PCC, RMSE, and CCC; classification metrics
  remain secondary.
- Hardware confirmation: placement-level metrics and bootstrap confidence
  intervals over placements, never over windows alone.

## Required confirmatory collection

After v3 is frozen, collect at least three new independent placements,
preferably on a different day. Use 16 s static, 40 s controlled cable motion,
24 s recovery, plus open-contact and restored conditions. Record exact action
times, packet loss, device configuration, and raw-file hashes.

# Frozen SQI v2: three-placement Cyton bench report

## Scope

This report concerns engineering signal-quality detection on a wet-gauze Cyton
bench arrangement. It does not validate physiological EEG, vigilance labels,
fatigue accuracy, emotion recognition, or BCI control.

The model, calibration rule, and SQI threshold (0.90) were frozen before the
second and third placements. No real bench condition was used to refit the
quality model or select a new threshold.

## Primary result

Across three independent electrode re-placements performed with the same
device, operator, and day:

- affected channel-windows: 88 detected, 19 missed;
- unaffected channel-windows: 939 accepted, 2 falsely rejected;
- pooled descriptive sensitivity: 82.24%;
- pooled descriptive specificity: 99.79%;
- pooled descriptive balanced accuracy: 91.02%;
- placement-level balanced accuracy: 93.79%, 90.37%, and 89.19%;
- placement-cluster bootstrap 95% interval: 89.19%-93.79%.

The window counts are descriptive and are not treated as independent subject
replicates. With only three same-day placements, the bootstrap interval is
illustrative rather than population-level evidence.

## Result by failure mechanism

- Single-channel open contact: sensitivity 86.96%, specificity 100%.
- Three-channel open contact: sensitivity 86.96%, specificity 100%.
- CH4 cable motion: sensitivity 53.33%, specificity 99.05%.
- Known-clean conditions: specificity 99.82%.

The predeclared overall transfer criterion was met, but the mechanism-specific
criterion failed for cable motion. This negative result is retained.

## Motion diagnosis

The CH4 motion-to-static robust-amplitude ratios were 16.83, 7.25, and 2.74
for placements R1-R3; corresponding motion-window detection fractions were
100%, 40%, and 20%. In R3, however, derivative MAD increased 24.92-fold and
31-50 Hz power accounted for 81.99% of 1-50 Hz power. The current SQI therefore
misses some lower-amplitude but fast/high-frequency cable artifacts.

This observation motivates explicit raw-domain transient descriptors. Because
that design decision was informed by R1-R3, these recordings become
development evidence for SQI v3 and cannot be reused as its final confirmatory
test.

## Transport notes

- R2-B1 packet loss: 0.077%; R2-B4: 0.020%; other R2 files: 0%.
- R3-B3 packet loss: 0.625%; R3-B5: 0.377%; other R3 files: 0%.
- These files were retained and the loss rates recorded. Neither restored
  condition generated SQI failures.

## Reproducible artifacts

- Placement aggregation: `aggregate_real_cyton_sqi_rounds.py`
- Aggregate machine-readable result:
  `results/real_cyton_sqi_three_placement_summary/summary.json`
- Motion diagnosis: `diagnose_real_cyton_motion.py`
- Motion descriptors:
  `results/real_cyton_motion_diagnosis/motion_descriptors.csv`
- Per-placement manifests and window scores:
  `results/real_cyton_sqi_v2_transfer`,
  `results/real_cyton_sqi_stage_b_round2`, and
  `results/real_cyton_sqi_stage_b_round3`.


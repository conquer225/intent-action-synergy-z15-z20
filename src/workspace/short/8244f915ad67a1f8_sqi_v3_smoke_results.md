# SQI v3 raw-feature smoke results

## Decision

Do not launch the full 21-participant experiment with the current v3 training
recipe. The pipeline is numerically valid, but the added raw features did not
improve participant-held-out cable-motion sensitivity.

## Four-participant exploratory results

At test severity 0.75 after training at severity 0.70:

- v2 cable-motion sensitivity: 88.13%; specificity: 96.15%.
- v3 cable-motion sensitivity: 88.13%; specificity: 95.73%.
- v3 provided no motion benefit and slightly reduced specificity.

At weak test severity 0.25 after training at severity 0.70:

- v2 sensitivity: 62.81%; specificity: 96.77%.
- v3 sensitivity: 48.75%; specificity: 99.06%.

At matched train/test severity 0.25:

- v2 sensitivity: 72.19%; specificity: 96.67%.
- v3 sensitivity: 65.00%; specificity: 99.79%.

The added raw features consistently made the model more conservative: clean
false-bad rate improved substantially, but weak-motion sensitivity decreased.
This is not sufficient for the stated v3 hypothesis.

## Interpretation

The failure is not evidence that the raw descriptors contain no useful motion
information; direct Cyton diagnosis showed strong derivative and high-frequency
signatures. It shows that the current single-severity regression target plus a
fixed 0.90 threshold does not trade sensitivity and specificity appropriately.

## Required revision before a full run

1. Train on multiple severities per corruption family rather than one fixed
   severity per recording.
2. Compare continuous quality regression with a class-balanced bad-channel
   classifier.
3. Select the operating threshold using training participants only, under a
   predeclared clean false-bad constraint of at most 15%.
4. Keep frozen v2 with threshold 0.90 as the deployment baseline.
5. Repeat the four-participant smoke test. Proceed to all 21 participants only
   if v3 improves weak-motion balanced accuracy without violating the clean
   false-bad constraint.

These results are exploratory and must not be reported as the final benchmark.

## Frozen-candidate smoke test after revision

The revision used multi-severity training, a balanced bad-channel classifier,
training-participant-only threshold selection, electrode-pop transients, and
two causal peak descriptors (maximum absolute amplitude and derivative).

At weak test severity 0.25 across all six corruption families:

- clean false-bad rate: 8.19%;
- flatline sensitivity / balanced accuracy: 100.00% / 97.08%;
- broadband-noise sensitivity / balanced accuracy: 100.00% / 95.73%;
- mains-noise sensitivity / balanced accuracy: 100.00% / 95.16%;
- drift sensitivity / balanced accuracy: 75.63% / 84.95%;
- burst sensitivity / balanced accuracy: 82.19% / 87.50%;
- cable-motion sensitivity / balanced accuracy: 98.13% / 93.75%.

The predefined continuation conditions are met: weak cable-motion balanced
accuracy improves over the DE-only regression baseline, cable-motion
sensitivity exceeds 80%, and clean false-bad rate remains below 15%. Drift is
retained as an explicit secondary weakness; no further smoke-set tuning is
allowed. The candidate now advances to the full 21-participant, three-severity,
three-seed experiment. These smoke results remain development evidence only.

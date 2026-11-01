# SQI v3 frozen full-protocol results

## Scope

This report covers signal-quality detection only. It does not yet establish
that quality gating improves vigilance-estimation RMSE, PCC, or CCC.

The frozen protocol used:

- 21 SEED-VIG participants (23 recordings);
- participant-grouped outer leave-one-subject-out evaluation;
- eight symmetric channels: FT7, FT8, CP1, CP2, P1, P2, O1, O2;
- 15 clean 8-second windows for per-recording calibration;
- training corruptions at severities 0.25, 0.50, and 0.75;
- tests at the same three severities with three deterministic seeds each;
- six corruption families: flatline, broadband noise, 50 Hz mains noise,
  slow drift, electrode-pop burst, and cable motion;
- classifier thresholds selected using training participants only under a
  clean false-bad constraint of at most 15%;
- participant-level paired statistics, 10,000 participant bootstraps, and
  Holm correction across six corruption families.

The baseline named `v2` in the result files is a DE-feature quality regression
baseline retrained under the same synthetic protocol. It must not be described
as the already deployed frozen hardware SQI v2.

## Primary frozen-candidate results

Across all nine runs, the v3 classifier achieved:

- clean false-bad rate: 2.02% (run standard deviation 0.22 percentage points);
- flatline balanced accuracy: 98.46%;
- broadband-noise balanced accuracy: 98.51%;
- mains-noise balanced accuracy: 98.03%;
- drift balanced accuracy: 91.19%;
- burst balanced accuracy: 92.00%;
- cable-motion balanced accuracy: 97.34%.

Severity-specific v3-classifier sensitivity / specificity / balanced accuracy:

| Severity | Flatline | Broadband | Mains | Drift | Burst | Cable motion |
|---|---:|---:|---:|---:|---:|---:|
| 0.25 | 98.37 / 97.31 / 97.84 | 96.83 / 98.12 / 97.47 | 97.84 / 97.76 / 97.80 | 80.65 / 97.76 / 89.21 | 76.29 / 97.33 / 86.81 | 93.67 / 98.62 / 96.14 |
| 0.50 | 99.96 / 97.68 / 98.82 | 99.90 / 97.92 / 98.91 | 97.46 / 97.61 / 97.54 | 86.65 / 97.59 / 92.12 | 87.32 / 98.00 / 92.66 | 96.01 / 98.48 / 97.25 |
| 0.75 | 99.90 / 97.55 / 98.72 | 99.96 / 98.33 / 99.15 | 99.64 / 97.84 / 98.74 | 86.43 / 98.04 / 92.24 | 94.76 / 98.30 / 96.53 | 99.25 / 98.03 / 98.64 |

Values are percentages and are ordered sensitivity / specificity / balanced
accuracy. Clean false-bad rate was 2.02% at each test severity because the
same clean held-out recordings are evaluated in each severity group.

## Participant-level paired comparison

The comparison is v3 classifier minus the DE-only regression baseline after
averaging the nine runs within each held-out participant.

| Corruption | Baseline BA | v3 BA | Mean change | Participant bootstrap 95% CI | Holm-adjusted p |
|---|---:|---:|---:|---:|---:|
| Flatline | 98.46% | 98.46% | +0.01 pp | [-0.85, +0.80] pp | 1.0000 |
| Broadband noise | 98.15% | 98.51% | +0.36 pp | [-0.43, +1.21] pp | 1.0000 |
| Mains noise | 97.01% | 98.03% | +1.01 pp | [-0.33, +2.20] pp | 0.0567 |
| Drift | 50.46% | 91.19% | +40.73 pp | [+36.27, +44.28] pp | 0.0000057 |
| Burst | 88.10% | 92.00% | +3.91 pp | [+2.48, +5.44] pp | 0.0000906 |
| Cable motion | 96.40% | 97.34% | +0.94 pp | [-0.15, +2.16] pp | 0.1745 |

The defensible statistical claim is that raw-domain v3 features materially
improve slow-drift and electrode-pop detection while preserving strong
performance on the other families. Cable-motion detection is excellent in
absolute terms but is not significantly better than the strong DE-only
synthetic baseline at participant level.

## Limitations and interpretation

1. Synthetic labels establish controlled detection performance, not complete
   ecological validity. The next evidence tier must use untouched Cyton
   placements R4+ with action timestamps and placement-level intervals.
2. Weak burst sensitivity is 76.29%; low-amplitude contact transients remain
   the hardest condition and should be disclosed.
3. The current comparison does not yet show downstream vigilance benefit.
   The gating model must be inserted into identical fatigue-estimation LOSO
   folds and evaluated on clean and corrupted PCC, RMSE, and CCC.
4. R1-R3 hardware recordings remain development data and cannot be reused as
   confirmation evidence.
5. The present results support an SQI/missingness-robustness contribution. They
   do not by themselves support claims about ViFormerNet accuracy or PYNQ
   latency/resource use.

## Decision

The frozen SQI v3 candidate passes the synthetic full-protocol stage. Do not
retune it using these test outputs. Proceed in this order:

1. evaluate downstream fatigue estimation with and without v3 gating under
   identical participant splits;
2. implement the fixed candidate in the PC/PYNQ streaming path;
3. collect at least three untouched Cyton placements R4+ for confirmatory
   hardware evaluation;
4. only after those steps, draft the final EI paper claims and figures.

## Reproducibility artifacts

- `run_raw_sqi_v3_full.py`: resumable nine-run protocol;
- `analyze_raw_sqi_v3_full.py`: participant-level statistics;
- `results/raw_sqi_v3_full_frozen/all_run_metrics.csv`: run-level metrics;
- `results/raw_sqi_v3_full_frozen/severity_summary.csv`: severity summaries;
- `results/raw_sqi_v3_full_frozen/participant_paired_values.csv`: paired values;
- `results/raw_sqi_v3_full_frozen/aggregate_summary.json`: aggregate metrics;
- `results/raw_sqi_v3_full_frozen/participant_statistics.json`: corrected tests.

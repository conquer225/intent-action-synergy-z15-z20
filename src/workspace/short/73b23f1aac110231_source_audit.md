# Source audit: emotion recognition and SSVEP

Audited source root: `D:\ican\整理`  
Audit date: 2026-09-22

## Scientific decision

The first falsifiable target is:

> A training-free five-target CCA baseline using Cyton posterior channels can
> exceed chance performance on untouched real trials and run on Z15 ARM with
> acceptable end-to-end latency.

The idea is rejected if participant/session-held-out real trials do not exceed
chance with a useful confidence/rejection tradeoff.  A synthetic self-test is
only an implementation check.

Emotion recognition is a separate experiment.  It must not reuse an SSVEP
accuracy claim, and it needs participant/session-safe evaluation before board
deployment.

## SSVEP assets found

- PyQt stimulus/application UI in `2026...\ssvep\window.py`.
- Five target frequencies: 7.3, 8.2, 9.3, 10.4 and 11.5 Hz.
- One-second, 250 Hz CCA decoding with three harmonics.
- Five template files and one combined template, each containing arrays shaped
  `(5, 8, 225)`.
- Alternative EEGNet, SSVEPNet and ConvCA class definitions, but no matching
  training dataset or trained checkpoint.

### SSVEP blockers in the supplied program

- `main.py` defaults to UI-only mode (`runmod = 0`), so decoding never starts.
- Runtime dependencies such as `keyboard` are absent in the current PC Python
  environment, and `main.py` imports a local `test` module that is not supplied.
- The decoder consumes LSL but the included BrainFlow setup is not connected to
  that LSL path.
- It takes seven EEG channels plus an eighth EOG/control channel, while the
  current Z15 acquisition path treats all eight as EEG.  A channel manifest is
  required before use.
- Display opacity is assigned `sin(...)`, which ranges from -1 to 1 although Qt
  opacity is defined on 0 to 1.  The intended modulation should be verified and
  clipped/mapped explicitly.
- A 1 ms Qt repaint timer is not evidence of the emitted display frequency.
  Frame presentation timestamps or a photodiode measurement are needed.
- The fixed CCA score cutoff `0.5` is not supported by a calibration report.
- The supplied templates are not referenced by the realtime decoder, and their
  provenance, channel order and stimulus timing are undocumented.

## Emotion assets found

- One SEED-style recording, `15_20131105.mat`, containing 15 trials with 62
  channels, and a 15-label file.
- An image-CNN training script and an LSL realtime inference script.

### Emotion blockers in the supplied program

- Only one participant/session is packaged; the README states that the full
  source dataset is about 9.62 GB.
- Training expects `/root/autodl-tmp/merged.csv`, but neither the CSV nor its
  generated images are present.
- No emotion checkpoint is present anywhere under `D:\ican`.
- Training instantiates `EnhancedCNNModel`; realtime inference instantiates the
  different `CNNModel`.  A checkpoint from the former cannot be loaded into the
  latter.
- The label mapping is reversed in the realtime display: training maps `-1` to
  class 0, while inference displays class 0 as `positive`.  In SEED, `-1` is
  negative and `1` is positive.
- Training uses random image-level splitting, which can place highly related
  windows from one trial/participant in both train and test.
- Training evaluates the test split after every epoch, turning it into a tuning
  set rather than an untouched final test.
- Realtime assumes 256 Hz although Cyton provides 250 Hz in the current system.
- With a one-second `spectrogram` whose segment is also one second, the computed
  time dimension collapses to one bin and is broadcast across a 256-column
  image.  The resulting image does not represent the intended temporal map.
- The eight plotted sensor positions are generic coordinates rather than a
  documented physical channel montage.

## Required acceptance gates

### SSVEP PC baseline

1. Fix and log monitor refresh rate and stimulus frame timestamps.
2. Record labelled trials with a posterior montage; keep calibration and final
   test runs separate.
3. Report accuracy, information-transfer rate, decision time, rejection rate,
   confusion matrix and per-run packet loss.
4. Tune confidence only on calibration/validation trials.

### Z15 deployment

1. Reuse the exact PC CCA numerical core and verify prediction agreement.
2. Measure acquisition + filtering + CCA + postprocessing + API latency.
3. Identify ARM and PL operations explicitly.  Start ARM-only; add PL only if
   profiling and a stated acceleration claim justify it.

### Emotion baseline

1. Obtain the complete dataset and participant/session manifest.
2. Start with a deployable DE/PSD + LDA/SVM/HGB baseline before a CNN.
3. Split by participant or session before normalization and feature selection.
4. Report participant-level balanced accuracy and macro-F1 over at least three
   seeds; preserve an untouched test condition.

## Montage warning

SSVEP normally benefits from posterior/occipital electrodes, while emotion
recognition may prefer a different spatial distribution.  Do not silently use
the fatigue montage for both tasks.  During initial bring-up, use separate,
documented montages per task; consider a compromise montage only after both
baselines have been measured.

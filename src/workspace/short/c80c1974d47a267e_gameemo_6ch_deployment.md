# GAMEEMO shared six-channel deployment

Completed 2026-09-23 on Z15 ARM at 192.168.2.99. This is an experimental
game-condition classifier; no labeled Cyton emotion accuracy has been established.

## Channels and quality gates

The physical acquisition order remains F3, F4, C3, C4, T7, T8, O1, O2.
The emotion model selects F3, F4, T7, T8, O1, O2 by name. C3/C4 remain available
in acquisition and SQI but do not enter emotion inference. At least five of the
six model channels must be individually calibrated and have SQI weight >= 0.5.
Uncalibrated channels receive weight zero. Missing features are blended with
training-fold medians; they are not reconstructed EEG waveforms.

Fatigue remains disabled because its trained montage differs from this montage.
The existing PL transport limits and raw-interference warnings are unchanged.
Emotion feature extraction and LDA execute on ARM; this change makes no FPGA
acceleration claim and does not change the bitstream.

## Evaluation

Source: the existing GAMEEMO v3 archive, 28 participants and 112 preprocessed
recordings. The first four seconds of each record are excluded as filter warmup.
Evaluation uses 8,176 nonoverlapping four-second windows. Each of 28 LOSO folds
holds out one entire participant; scalers, medians and augmentation are fitted
only on the other participants. Game conditions provide the four class labels,
not individual self-report measurements of emotion.

Fixed preprocessing mirrors the runtime: resample public 128 Hz data to 250 Hz,
continuous 50 Hz notch (Q=5) and Butterworth order-4 1–45 Hz bandpass, followed by
the same window feature function as the board. That function resamples to 128 Hz
and computes band-major log variances in 4–8, 8–13, 13–30 and 30–43 Hz bands.
Vendor preprocessing/reference differences from Cyton remain a domain mismatch.

- Plain eight-channel clean balanced accuracy: 37.0597%.
- Plain six-channel clean balanced accuracy: 36.9007%.
- Six/eight retention ratio: 99.5710% (predeclared threshold 90%).
- Mask-augmented six-channel clean balanced accuracy: 35.4126%, seed SD 0.1257
  percentage points across seeds 13, 37, 73. Macro-F1: 0.35174.
- Average balanced accuracy across six single-channel missing conditions:
  plain 33.0867%, mask-augmented 34.0020%.

Thus masking trades about 1.49 percentage points of clean performance for about
0.92 points averaged over the declared missing-channel conditions. These are
descriptive results, not a significance claim. Missing-channel simulation is
not evidence of robustness to all natural electrode artifacts. The four-class
chance reference is 25%; the observed performance is modest.

The deployed model uses predeclared seed 13, not the best held-out seed, and is
refitted on all 28 public participants after evaluation.

## Runtime verification and deployment

`output/gameemo_6ch_live/board_validation.json` records PC/ARM agreement on the
public-data fixture at the runtime's four-decimal probability reporting precision.
Channel permutation with matching names preserves the output; changing unused
C3/C4 preserves it; five usable model channels pass and four are rejected;
a missing named model channel is rejected.

ARM feature extraction plus inference over 20 repetitions had median 122.67 ms
and p95 145.00 ms while acquisition was running. This excludes acquisition,
continuous stream filtering, SQI, network and PL time.

Production files and the service unit were backed up with suffix
`.before-sqi-20260923-225624`. Remote project:
`/home/xilinx/jupyter_notebooks/guardianloop_pynq`.
The previous local eight-channel model is retained at
`output/gameemo_6ch_live/previous_model_8ch.json`.

The board reported `EMOTION_MODEL_READY` for the six-channel model. The user
confirmed Cyton was powered off after the previous test, so no new live emotion
prediction was validated during this deployment. The next live check requires
Cyton in PC mode, powered on, receiver connected and the acquisition service
running. SQI recalibrates after service restart; five eligible channels each need
15 accepted windows, so two minutes is a lower bound rather than a guarantee.

The web UI calls the softmax value a model score, not measured accuracy, and
displays the six selected channels and five-of-six gate.

## Reproduce

From `D:\ican\codex_project`:

```powershell
python eeg_apps_z15/train_gameemo_shared_montage.py
python pynq_guardianloop/validate_emotion_on_board.py --artifacts eeg_apps_z15/output/gameemo_6ch_live
python pynq_guardianloop/deploy_sqi_update.py --emotion-model eeg_apps_z15/output/gameemo_6ch_live/model_6ch.json
```

Artifacts in `output/gameemo_6ch_live` include the data manifest with recording
hashes, predeclared protocol and folds, all fold predictions, per-participant
metrics, seed results, model, public-data runtime fixture and board validation.
The existing eight-channel baseline outputs have been retained.

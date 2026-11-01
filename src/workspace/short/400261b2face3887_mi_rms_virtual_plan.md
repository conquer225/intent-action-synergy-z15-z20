# Shared-RMS MI: isolated virtual-control integration (2026-10-03)

## Scope and acceptance, fixed before running

Use the previously accepted, frozen shared-RMS EEGNet and fixed channel order
`F3,F4,C3,C4,T7,T8,O1,O2`. No training, label swapping, per-channel scaling,
threshold changes, live serial input, actuator, PL access, service replacement,
or startup changes. All processing for this candidate runs on ARM.

The input is the existing 39,000-sample / 156-second bench load recording.
It is not labeled MI and cannot validate recognition accuracy. Prompt labels
only select a test window. Compare observation versus virtual control under
identical filtering, quality checks, sample windows and model outputs.

Required checks:

- Existing cue, virtual-control and RMS numerical tests pass on PC and ARM.
- All 13 complete candidates produce exactly one virtual command when opted in;
  observation produces none. Every command follows the model, not the prompt.
- Observation and virtual modes have identical filters and logits. PC/ARM logits
  agree within absolute `1e-4`, with identical classes, windows and command actions.
- The private HTTP page explicitly identifies recorded input and the new model.
  Start is refused without warm, fresh replay input. Replay requires manual start,
  never loops automatically, and cannot accept uploaded EEG or supplied answers.
- Actual HTTP start/presentation/heartbeat generates one model-derived virtual
  command; repeated polling does not move again. Hidden-page stop, replay stop,
  EOF and restart withdraw old results; rest does not invoke the classifier.
- The official file hashes, service PIDs/restart counts, boot identity and current
  MI configuration remain unchanged. No ongoing recording may be interrupted.

Only leave the isolated page running if all gates pass. It must be idle at handoff
and must have a documented exact-PID stop command. No permanent systemd unit is
installed. The original formal page remains at port 9102.

This step establishes the functional replay-to-virtual-hand loop, not personal
accuracy, a model promotion, total multi-task production latency, or FPGA speedup.

# Real Cyton SQI transfer protocol v1

## Purpose

Test whether the frozen SQI v2 ranking learned from synthetic corruption transfers
to real Cyton acquisition states. This protocol does **not** validate fatigue
accuracy and requires no vigilance labels.

Primary hypothesis: SQI v2 assigns lower quality to controlled channel-contact
failures than to a stable conductive reference state, and quality recovers after
contact is restored.

Falsification condition: SQI v2 cannot separate stable and degraded states, or
does not recover after restoration, under the preregistered analysis.

## Fixed acquisition metadata

- Board: OpenBCI Cyton, 8 channels
- Sampling rate: 250 Hz
- Power: Cyton battery only
- Receiver for Stage A: OpenBCI USB dongle connected to the PC
- Software: OpenBCI GUI
- Recording format: OpenBCI RAW text plus BrainFlow CSV when available
- Channel order: CH1--CH8 (physical scalp labels are not applicable during bench testing)
- Reference/BIAS: record their physical bench arrangement in the manifest notes
- Online display filters do not replace analysis-time preprocessing

## Stage A: non-human bench recording

Keep one continuous recording if possible. Leave at least 10 seconds between
states and write the exact GUI clock time at every transition.

| State | Duration | Action | Expected interpretation |
|---|---:|---|---|
| B0_floating_insulated | 60 s | Electrode cups rest separately on a dry insulating surface | Deliberately bad/open-input state; railing is expected |
| B1_common_conductive | 120 s | Put all eight cups plus reference/BIAS in separate contact with one stable saline-moistened gauze pad; do not short board pins directly | Stable phantom-like reference, not physiological EEG |
| B2_single_open | 60 s | Lift CH1 cup away from the pad; keep all others unchanged | One-channel contact failure |
| B3_multi_open | 60 s | Lift CH1, CH2, and CH3 | Multi-channel contact failure |
| B4_cable_motion | 60 s | Restore all cups, then gently move only the CH4 lead near the cup | Motion/transient stress |
| B5_restored | 120 s | Stop moving and restore the stable conductive arrangement | Recovery condition |

If saline gauze is unavailable, collect B0 only, then stop. Do not substitute an
unknown conductive liquid or electrically connect the inputs to mains-powered
equipment.

## Stage B and Stage C

- Stage B repeats the bench states with the USB dongle connected to Z15, to
  separate receiver/software effects from signal-quality effects.
- Stage C is a short 10--15 minute human recording with stable contact, natural
  hair obstruction, controlled loosening, movement, brief disconnection, and
  recovery. It is performed later and is required before making a real-contact
  transfer claim.

## Acceptance checks

1. Each state has at least 45 usable seconds after transition exclusion.
2. Sample count is consistent with 250 Hz and timestamps are monotonic.
3. Packet loss, railing/clipping, robust scale, drift, mains ratio, high-frequency
   ratio, transient rate, and inter-channel correlation are reported separately.
4. B1 and B5 are not called clean EEG; they are stable bench references.
5. Synthetic-to-real comparison uses distributions and event morphology, not
   amplitude alone.


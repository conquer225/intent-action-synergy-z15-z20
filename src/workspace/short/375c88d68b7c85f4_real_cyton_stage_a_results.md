# Real Cyton SQI transfer: Stage A bench results

## Scope

Stage A is a non-human bench validation of acquisition continuity and controlled
contact-failure signatures. It does not contain physiological EEG and cannot
validate fatigue accuracy. Cyton was battery powered and the OpenBCI USB dongle
was connected to the PC.

## Fixed conditions

- OpenBCI Cyton, 8 channels, 250 Hz.
- Stable reference: eight gold cups, SRB2 and BIAS on folded saline-moistened
  gauze over an insulating tray.
- Analysis windows were declared before inspecting the outcomes.
- Packet continuity was assessed from modulo-256 sample indices; signal railing
  was assessed separately.

## Main observations

1. **B0 floating/insulated:** severe open-input behavior occurred while packet
   continuity remained intact. This confirms that poor signal quality must not
   be equated with RF packet loss.
2. **B1-R stable conductive reference:** the final 60 seconds had zero estimated
   packet loss and zero railing on all channels. This is the accepted bench
   reference, not clean EEG.
3. **B2 CH1 open:** in the fixed 10--70 second window, CH1 railing was 17.90%
   and its MAD was 116,350 uV; CH2--CH8 had zero railing and packet loss was 0%.
4. **B3 CH1--CH3 open:** railing was 16.99%, 11.25%, and 26.90% for CH1, CH2,
   and CH3 respectively; CH4--CH8 had zero railing and packet loss was 0%.
5. **B4 CH4 cable motion:** CH4 MAD increased from 65.3 uV in the pre-motion
   interval to 1,099.4 uV during motion. CH5, CH7 and CH8 also changed, showing
   that a real mechanical artifact may be spatially coupled rather than perfectly
   isolated to the manipulated channel. No channel railed and packet loss was 0%.
6. **B5 restored:** over the fixed 120-second recovery window, packet loss and
   railing were both 0%. CH4 MAD recovered to 67.3 uV, close to its 65.3 uV
   pre-motion value.

## Decision

Stage A supports the engineering claim that contact failures and cable-motion
artifacts can be separated from RF packet loss and that recovery is measurable.
It does not yet establish transfer to hair/skin contact or physiological EEG.

The next analysis step is to compute the frozen SQI v2 score on fixed windows
from B1-R through B5 and compare score ordering with the declared conditions.
After that, repeat the minimum protocol on Z15 and perform a short human Stage C
recording before making a real-contact robustness claim.


# Protocol reference

`third_party/njmill/tobii-ttp-mux.c` and `LICENSE` were obtained from
https://github.com/njmill/tobii-linux at commit `4b231c3f3194047209a630f495416256a037175b`.
License: Apache-2.0, preserved in that directory.

Original source SHA-256: `1fcc88373a9029b983522ed6cc34c1052f62254a4daad0957589a9f583e3fa53`.
Original hardware target is ET5 `2104:0313`, not the connected IS4 OEM.
`tools/make_is4_probe.py` creates a separate experimental source with PID `0124`,
minimal protocol startup and bounded response dumps. The generated adapter also
corrects the connected IS4's column meanings, rejects incomplete samples, separates
fragment accumulation from timeouts, matches responses by sequence and operation,
and adds read-only metadata/calibration backup queries and resource telemetry.
Basic compatibility has now been demonstrated on the actual ARMv7 board; valid
person tracking and calibration compatibility remain unverified.
No firmware flashing code is included or run by this probe.

The adapter now retains the response header words at offsets 8 and 16,
rejects nonzero firmware status, and avoids treating invalid public-realm
challenge replies as success. `src/calibration.c` includes the generated
adapter to reuse its credited framing and strict IS4 gaze decoder; its timed
worker, backup/readback rollback and UI bridge are separately written here.
Firmware error meanings were checked against Tobii's Analytics SDK Developer's
Guide Appendix 2 (manufacturer-authored manual mirrored at
https://manualzz.com/doc/39694095/tobii-analytics-sdk-eyetracking-software-developer%E2%80%99s-guide).
Vendor x86-64 library serialization was inspected locally, never run on Z15
or incorporated as an executable dependency.

Protocol facts were cross-checked against Tropaion/Tobii_Linux at commit
`71639383863fee69ff304efc5bb2173a6683896d` (GPL-3.0), and against the
connected device's stream catalog and gaze schema. No Rust code is incorporated
into the adapter or the independently written Python decoder.

`third_party/talon_init_out.txt` is an ignored local inspection artifact from
https://github.com/simonvc/tobii_ffg/blob/main/captures/talon_init_out.txt.
It is not a dependency, was not replayed against this module, and is not part of
the distributable source. In particular, its display writes were not applied.

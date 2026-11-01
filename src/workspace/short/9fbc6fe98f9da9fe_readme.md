# Z15 HDMI audio candidate (not deployed)

User authorized isolated reconstruction, simulation, synthesis, implementation
and candidate bit/hwh generation on 2026-10-16. **Board loading is not authorized.**
Do not modify either installed overlay or SD boot configuration.

Third-party HDMI source is pinned to `hdl-util/hdmi`
`83b1c9543a91b776671a44e68e130f81cae437b7`, MIT OR Apache-2.0.
Keep upstream license files. Two locally patched modules add an optional sample
enable; see `third_party/PATCHES.md`. No third-party HDL is installed on Z15.

`rtl/pcm_buffer.sv` is the PCM16 stereo AXI-Lite FIFO candidate. It is NOT
assigned a board address until the isolated block design reserves one.
Offsets: 0x00 identity, 0x04 control (bit0 enable, bit1 held reset),
0x08 queued words, 0x0c reset/full/busy flags, 0x10 PCM write,
0x14 underruns, 0x18 usable FIFO capacity (depth minus one), 0x1c sample rate.
Stop/flush: write control=2; hold at least 5 sample clocks, write control=0,
wait for busy to clear, fill new PCM, then write control=1.
Start is never automatic after reset. No output peripheral is accessed by simulation.

The existing display contract must be retained: VDMA0 0x43000000,
VDMA1 0x43010000, OSD 0x43c00000 (identity 0x4f534438, scan counter at +0x0c),
VTC 0x43c10000. Existing source is not available; the reconstructed design is
not yet a drop-in replacement. No final bitstream exists yet.

## Verified offline milestones

The real XPM FIFO simulation tests overflow rejection, independent AXI AW/W
arrival, response backpressure, sample order, reset/flush and underrun silence.
HDMI packet tests decode packet bits and check BCH, stereo PCM16 alignment and
order, IEC parity/status, InfoFrame checksums and N/CTS. The external-video test
decodes TMDS symbols and compares every active RGB pixel and HS/VS, video and
data-island guard/preamble placement against the independent input raster.
The serializer test uses AMD's actual OSERDESE2 simulation primitive, not a
behavioral substitute, for bit order and the forwarded clock lane.

Use `run_simulation.py --suite pcm|packets|video|serial --output NEW_DIRECTORY`.
Upstream packet primitives are reused with the documented optional-enable patch, while
`hdmi_external_video.sv` follows the existing VTC instead of introducing another
independent video generator. `hdmi_audio_tx.sv` uses the user's board-vendor
`serializer_10_to_1.v` in place of upstream's platform-dependent serializer.
Vendor source stays in its original tree and retains its original copyright.
`MODEL_TECH` only selects defined zero values for protocol-ignored bits in
simulation; synthesis still reads the original upstream source.

## Clock contract — final candidate uses sample enable, not a fabric clock

Legacy HWH requests 150 MHz on PS FCLK1 but **actual** frequency is
142.857132 MHz (IO PLL / 7). The 48 kHz divider requires an exact 150 MHz input.
`verify_clocks.tcl` validated a new MMCM configuration on xc7z015clg485-2:
100 MHz input, multiplier 7.5, input divider 1, output dividers 10/2/5 give
75/375/150 MHz. Audio clock division by 3125 gives 48 kHz; stable ACR is
N=6144 and CTS=75000. This clock IP is generated locally only. Existing board
clock settings have not been changed. Integration must use the new MMCM output
and must not assume requested PS frequency equals actual frequency.

The first complete candidate (`output/full_09`) used that 150 MHz / 3125 clock.
Although bitgen succeeded, post-route review found long-period TIMING-8/CDC
findings. It is **not a board-test release** and has never been loaded. The
clock-ratio audit preserved under `output/clock_audit_03` showed that spelling
the divider differently does not remove these findings. No false clock group or
DRC severity waiver was used to hide them.

`full_10` replaces the slow clock with `audio_sample_tick.sv`: audio capture,
FIFO read and HDMI packets share the existing 75 MHz pixel clock, with exactly
48 enables per 75000 pixel cycles (alternating 1562/1563-cycle intervals).
The patched upstream ACR counts actual enables; its stable CTS remains 75000.
The 150 MHz MMCM output is no longer used to clock audio. The old divider stays
only as a separate-clock simulation reference for the inherited packet modules;
it is not instantiated in the new BD.

`full_10` routed with no critical CDC or methodology findings, but failed setup
timing (WNS -0.217 ns, eight endpoints). Bit generation was correctly blocked.
The failing path was the host-domain `held_reset` gating the FIFO read enable.
`full_11` removes that redundant combinational gate: the existing asynchronous
reset of `run_sync` already mutes and stops the read side. Simulations
`pcm_sim_13`, `pcm_ticks_sim_03`, and `pcm_capacity_sim_03` explicitly check
software and hardware resets while nonzero audio is presented. All passed.
This source fix was then checked by new full place/route reports below; it is
not a timing waiver or evidence of audible output.

Final `full_11` evidence: routed setup WNS +0.547 ns, hold WHS +0.019 ns,
zero failing setup/hold endpoints and zero unconstrained internal endpoints.
Final DRC has no errors/critical warnings; CDC has 25 CDC-3 info, 12 CDC-9 info
and 10 CDC-15 warnings in inherited AXI clock converters. Methodology retains
vendor AXI reset warnings and camera input-delay warnings, without criticals.
Do not claim all build logs are warning/error-free: synthesis reports a missing
pre-insertion camera clock net on the vendor physical constraint, and a directory
creation message, despite successful final implementation and bit generation.
`review_routed_candidate.tcl` separately verifies that the actual routed camera
net has the vendor CLOCK_DEDICATED_ROUTE setting. Camera capture timing is not
qualified by this HDMI audio candidate.

Candidate artifacts (not loaded):
`output/full_11/candidate/guardianloop_display_audio.bit` SHA256
`ef60c903c519efb7b4eb5dbcadca1594208f5049207e1a92e422b918dbaae2f6`;
matching `.hwh` SHA256
`e7c3bcb9024393fba331f6b0c9b85b4a488832555c06309142703b308819767d`.
Board loading, low-volume speaker confirmation and unified UI integration still
require their own controlled steps. No runtime file was overwritten by this build.

The depth-8192 FIFO simulation exposed that XPM's usable FWFT capacity depends
on its implementation. The AXI peripheral now explicitly enforces the declared
8191-word public capacity, including its full flag; the real-depth simulation
checks all 8191 stereo words and refuses the next write. Both enable-gated and
legacy read-clock simulations remain (`pcm_ticks`, `pcm_capacity`, `pcm`).

## Component synthesis is not a finished overlay

`run_synthesis.py --output NEW_DIRECTORY` requires current passing simulations
and runs out-of-context synthesis for PCM buffer, sample divider and transmitter.
Reports/checkpoints are local. Synthesis reports are **not** board or full-design
timing evidence. In an isolated transmitter DRC, UCIO-1 (unassigned output pins)
and ZPS7-1 (PS7 absent) are expected, unresolved integration findings, not waived
checks. No DRC severity is reduced. Resource totals cannot replace full-design
place/route, CDC and timing analysis.

`rebuild_display.py` now reconstructs the inherited PS/VDMA/VTC/camera connection
graph and editable configuration from the installed HWH. It replaces only the
DVI transmitter and the missing `live_osd` source. `display_status.sv` implements
the identity/scan-counter ABI actually used by the display library, with video
passthrough; other old OSD registers are not claimed as reproduced. Its AXI,
scan-count CDC/reset and passthrough behavior have an independent simulation.
The candidate PCM address is **0x43c20000**; this is NOT an address to access with
the old overlays loaded. Existing four display addresses are unchanged.

Pin assignments are extracted from the user's vendor Z15 project constraints,
not guessed: HLS `5_ov5640_rgb2gray/.../pin.xdc` for camera/SCCB and Embedded Linux
`system.xdc` for HDMI. Their source hashes are recorded per reconstruction.
`verify_display_contract.py` checks inherited PS DDR/MIO configuration, VDMA,
VTC raster, addresses, clock outputs and actual PCM/video connections against
the original HWH. Negative controls intentionally corrupt these values.

`run_implementation.py` drives local full synthesis/place/route and only writes
the distinctly named candidate bit/hwh after its timing/critical-DRC gates.
The current full-build status must be read from that output directory, not
inferred from a component report or HWH validation. CDC and unconstrained I/O
timing require separate review before loading. Then seek board-loading approval.
Do not claim speaker output, A/V synchronization or eye/EEG coexistence from
these component tests.

## ARM PCM preparation/player

`pcm_player.c` consumes preconverted 48 kHz PCM16 stereo WAV. `--inspect` and
`--render` operate only on regular files and never map hardware. The exclusive
raw render path is used to check stereo ordering and integer volume scaling.
`--play` is a separate, **not yet authorised/executed** hardware operation: it
requires the candidate PCM identity, serialises access with one process lock,
prebuffers bounded samples, checks consumption, and stops/flushes on SIGTERM.
Its status does not claim measured audibility. Never invoke it on the old bit.

`stage_pcm_player.py` only stages/compiles/runs offline tests in a new private
Z15 directory. It does not install a service, change boot/runtime code, load
PL, or invoke `--play`. Unified UI/audio integration and actual A/V timing
measurements still remain, along with low-volume confirmation of the ARZOPA
speaker for video, music and both communication phrases.

`audio_session.py` is the candidate display-side process owner. It keeps a single
latest requested audio state, handles child teardown away from the display
thread, drains bounded status/error reports and refuses successful close while
a PCM child is still alive. Replacing a track waits for the previous child;
natural completion does not replay it. Position is an estimate from the PCM
backend, not a measurement of HDMI/speaker latency. The process-lifecycle tests
use `sim/pcm_player_process_stub.py`, which cannot access audio hardware.
This helper is not installed in the running display and has not yet been wired
to the live page/selection events.

The C player now installs its stop handler before mapping/reset/prebuffering,
not only after prebuffering. Private stage `gl-pcm-player-20261016-TA9R7U` passed
GCC -Wall -Wextra -Werror and all 13 file/process tests on Z15 Python 3.8;
evidence is `output/player_arm_03/`. Its four actual assets were inspected only,
with `hardware_opened=false`. That evidence proves neither MMIO playback nor
physical sound. Candidate bit/hwh remain unchanged and no running service was
updated, stopped or restarted.

## Controlled board evidence (after separate authorisation)

The later `board_trial_01`/`04` runs temporarily loaded `full_11`, exercised PCM
consumption and restored the original overlays/services. A restore race in the
first run was traced to a stale stopped/expired player status; recovery now
publishes fresh starting state, waits for a ready homepage, then starts the old
watchdog. No original bit/program/boot file was overwritten.

Source-level RMS measurements explained the quiet speech/video. `level_audio.py`
creates fixed-gain copies with a -3 dBFS peak ceiling; five file tests passed
locally and on Z15. The original assets remain unchanged. Files and hashes are
under `output/levels_01` and `/home/xilinx/gl-audio-level-20261016-DMoJIj/`.

In **`board_trial_05`, at 40% digital volume**, the user explicitly confirmed both
leveled Chinese phrases were clear on the ARZOPA speaker (each played twice).
`user_confirmation.json` records the human observation separately from the
backend status. The original homepage/services were then verified fresh, and
the acquisition PID stayed unchanged. This is real speech audibility evidence,
not proof of music/video quality or completion of unified UI integration.
Those remaining tasks, volume control and A/V sync still need implementation
and verification; the old restored UI is intentionally still silent.

## Unified audio candidate (not installed)

`page_audio.py` now connects actual `SystemController` receipts to the existing
PCM child owner. Speech requires a new accepted speech-page selection; repeated
polls and returning to the page cannot replay an old phrase. Deliberate new
selection can repeat it. Music plays the one prepared song, and page exit stops
it. Video pause/resume, loop and switch use source-frame positions, not a
growing wall-time counter. Estimated audio/video offset is reported, not claimed
as measured speaker synchronisation. Missing tracks remain explicit silence.

`media_player.py` has an opt-in `hdmi_audio` session configuration; it verifies
the exact full_11 bit/hwh and player/assets hashes before enabling audio. The
old overlays cannot enable this backend. Audio child shutdown precedes PL/DMA
cleanup. Default sessions remain unchanged/silent. Audio-enabled shells use a
separate cache name, and the old static mute badge is replaced only when the
candidate backend is configured.

The local phone UI has a disabled-until-enabled 0..100 volume slider, applied
on release through the existing authenticated command path. Integers only;
unavailable audio rejects the command. Disconnection revokes the slider and
status. HDMI and phone labels distinguish submitted audio from measured sound.
No active phone/HDMI code or state file has been replaced by this work.

`output/player_arm_04` passed 22 ARM file/process/controller tests in private
stage `gl-pcm-player-20261016-OG3bQ1`, without MMIO, PL load or audible output.
Local checks passed 55 audio/controller/contract tests, 27 HTTP/command tests,
the existing JavaScript interaction suite with new audio checks, and 33 HDMI
tests (one board-fitter test skipped locally). Board UI checks intentionally
cover the two new HTTP volume / rendered audio-label cases, not full hardware
coexistence. The first broad board-render test (`unified_ui_01`) outlived the
SSH observation timeout; its process was confirmed exited before new checks,
and no result is claimed for that interrupted observation.

Still required: backed-up runtime installation with separate authorisation,
new-bit unified HDMI/eye/EEG coexistence, music/video audibility, measured A/V
behaviour under load, and preparation of audio for the rest of the video
library. The speech-only successful trial does not prove these requirements.

## Daily unified audio installed (2026-10-16)

The subsequent explicit installation authorisation supersedes the not-installed
status above. `output/unified_install_02` records the transaction at
`/home/xilinx/gl-hdmi-audio-installed-20261016-2jBKz1/`. The full_11 bit/hwh
remain separate from both original overlays. The seven tested UI/audio source
files, media configuration, current player configuration and boot checksum list
were backed up before replacement. ARM acquisition PID 13373 stayed unchanged;
no EEG calibration/model, SD boot image or motor command was changed.

The homepage now uses the audio candidate at 40% volume, with the phone slider
enabled. A real HTTP/controller acceptance sequence reached feeding state for
both phrases, music and the uploaded clip; 40→30→40 volume changes succeeded,
and returning home stopped the PCM child. The music feeding observations had
zero underruns; short speech completion reported small tail underrun counts,
so this is not a claim of universally underrun-free output. Full samples are in
`ui-acceptance.json`. The user subsequently confirmed the installed sequence
with “听到了  同步”; `user_confirmation.json` preserves that direct observation
separately from backend telemetry. This is perceived synchronisation, not an
instrument-measured latency bound. The requested speech/music/existing-video
speaker path is now audibly accepted.

SD cat/dog and the self-check clip have no source audio tracks. Only the existing
uploaded clip has a prepared video audio mapping. Newly uploaded video audio
preparation is not automatically connected yet. Eye/SSVEP operation with the
new PL has not been re-qualified by this audio-only acceptance sequence.

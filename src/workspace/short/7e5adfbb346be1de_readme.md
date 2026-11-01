# Z15 EEG Applications: SSVEP and Emotion

## Latest HP0 → DDR diagnosis — 2026-09-28

The 16-word DDR mismatch reproduces with only PS7 HP0 and also with the
unchanged vendor source explicitly rebound. A one-delta request-timing change
in an **isolated simulation-only copy** removes it; the complete filter + DMA
+ HP0 test then passes strict DDR contents and request-count checks in all
three scenarios. The **stock VIP still fails strict acceptance**, so this is
diagnostic evidence, not vendor/hardware qualification or PL deployment.
Nothing was synthesized, programmed or changed on Z15. See the
[diagnosis and all control logs](output/pl_hp0_ddr_diagnosis_v2025_2_20260928/RESULTS.md).

## Latest full-chain co-simulation checkpoint — 2026-09-28

The actual pipelined filter, vendor DMA, complete interconnect and full PS7
HP0 VIP now share one Vivado/XSim 2025.2 testbench. Interface-level drain,
transient-backpressure recovery and permanent-stall lockout cases pass, with
bit-exact HP R/W scoreboards. **Strict DDR end-to-end acceptance fails**:
the vendor DDR backend consumes previous write payloads and leaves the final
16 words stale. Waiting and disabling optimization did not fix it. The
explicit `-ObserveBackend` diagnostic mode does not qualify deployment.
The controller is testbench-only; the board, runtime fail-closed policy and
bitstream remain unchanged. See [evidence, scope and reproduction](output/pl_full_chain_cosim_v2025_2_20260928/RESULTS.md).

## Latest HP0/duplex reset checkpoint — 2026-09-28

Vivado/XSim 2025.2 now verifies FCLK-reset isolation using the official PS7
reset generator and HP0 AFI behavior model: pending read/write transactions
survive a PL FCLK reset. The same vendor DMA instance was also tested with
both directions simultaneously outstanding. PL-only reset reproduced stale
read data and old-buffer write corruption; draining both directions before
external reset passed. A permanently stalled software reset did not finish
and the test refused restart. This is behavioral co-simulation, not a silicon
or full filter/crossbar/HP0 integration acceptance. The production board and
candidate ARM fail-closed policy remain unchanged; no bitstream was generated.
See [scope, fourteen cases, preserved negative result and reproduction](output/pl_hp0_duplex_cosim_v2025_2_20260928/RESULTS.md).

## Latest reset-risk audit — 2026-09-27

The isolated candidate now has partial-frame software fault injection and
filter-stream mid-frame reset/recovery tests. Those pass, but the generated
DMA/interconnect still reports asynchronous-reset warnings. At that checkpoint
no vendor-DMA transaction-level proof existed; the newer audits above/below
supersede that limitation only within their stated simulation scope. Board
recovery remains unverified. See the [reset/DMA audit](output/pl_dma_inflight_audit_v2025_2_20260927_retry2/RESET_DMA_AUDIT.md).

## Latest isolated PL timing candidate — 2026-09-27

A separate registered-product SOS filter candidate passes full Vivado 2025.2
simulation, synthesis, and routing at 50 MHz with **+4.473 ns routed setup
slack**. It takes 50 rather than 25 processing cycles per word. The production
board is unchanged; DMA/reset warnings and hardware recovery are unresolved,
so no bitstream or deployment was performed. See the [candidate audit](output/pl_pipeline_route_v2025_2_20260927/RESULTS.md).

## Latest PL implementation checkpoint — 2026-09-27

The isolated Vivado 2025.2 filter/DMA candidate now reports a fully routed
50 MHz post-route physical-optimization checkpoint with zero failing timing
endpoints, but **0.000 ns setup margin**. It is not production-approved:
DRC/methodology warnings and live DMA reset recovery remain unresolved; no
bitstream or board changes were made. See the [post-route optimization evidence](output/pl_postroute_opt_v2025_2_20260927_retry1/RESULTS.md).

## Latest research checkpoint — 2026-09-26

Board-preprocessing matching has now been evaluated offline: 67.32% mean
subject balanced accuracy versus 67.58% with the original pipeline, on identical
nominal window keys. The predeclared two-point retention test passed; no board
model was changed. See [matched-preprocessing evidence and limitations](output/seed_matched_preprocessing_20260926/RESULTS.md).

Complete SEED fixed-eight-channel LOSO experiments now have a past-only
normalization candidate: mean subject balanced accuracy 67.58%, versus 59.56%
on identical windows without adaptation. This is exploratory SEED three-class
performance, not wearer accuracy, and the board has not been changed.
See [protocols, negative results, limitations and reproduction](SEED_CAUSAL_RESEARCH_20260926.md).
SEED/DEAP are now present under `D:\ican\datasets`; historical missing-data notes
below describe earlier stages, not the current inventory.

This directory is the clean migration workspace for the two EEG applications
found under `D:\ican\整理`.  The vendor/demo sources are kept unchanged.

## Fixed Cyton montage and next emotion experiment

The physical CH1–CH8 order is **F3, F4, C3, C4, T7, T8, O1, O2**. Keep this
unchanged for training and deployment. The earlier GAMEEMO eight-channel
experiment used AF3/AF4 instead of C3/C4 and is **not** an eight-channel model
for this headset. Its shared six-channel result remains an auxiliary baseline.

The [fixed protocol](fixed8_protocol.json) specifies true self-rating labels,
participant-separated development/holdout sets, and a Z15-local deployment
target. DEAP's preprocessed Python files have the exact eight electrode sites,
but access requires the user's signed [DEAP EULA](https://www.eecs.qmul.ac.uk/mmv/datasets/deap/doc/eula.pdf).
Only after obtaining the files from the official source, put `s01.dat` through
`s32.dat` in `D:\ican\datasets\DEAP\data_preprocessed_python` and run:

```powershell
python .\eeg_apps_z15\fixed8_deap_preflight.py D:\ican\datasets\DEAP\data_preprocessed_python
python -m unittest eeg_apps_z15/test_fixed8_deap_preflight.py -v
```

The preflight audits structure, electrode indices, ratings, completeness, and
file hashes. It does **not** train or claim accuracy. DEAP uses a different
device/reference and video stimuli; a future Cyton-labeled evaluation is still
required before claiming real-use emotion accuracy.

After a complete, licensed dataset passes preflight, the development-only
comparison is:

```powershell
python -m eeg_apps_z15.fixed8_deap_experiment D:\ican\datasets\DEAP\data_preprocessed_python
```

It evaluates four bands (theta/alpha/beta/low-gamma; the official preprocessed
DEAP data has already been high-pass filtered near 4 Hz), comparing log power,
log covariance, and a train-fold-only tangent reference. It reads no holdout
signals into the training pipeline and reports participant-level results and
raw predictions. s25–s32 are reserved until method selection is frozen.

## Current decision

1. Bring up **emotion recognition first**, using a deployable 8-channel
   five-band baseline and trial-safe evaluation.
2. Connect the same feature layout to Cyton only after the offline baseline and
   channel mapping are frozen.
3. Validate the exported model on PC and Z15 ARM before considering PL work.
4. Keep five-target SSVEP as the second application; its portable CCA baseline
   remains available below.

## SSVEP baseline

The portable baseline is in `ssvep_core.py`.  It uses only NumPy and implements
CCA against sine/cosine references for 7.3, 8.2, 9.3, 10.4 and 11.5 Hz.

Run the deterministic software self-test:

```powershell
python .\eeg_apps_z15\test_ssvep_core.py
```

Passing this test proves only that the implementation can recover known
synthetic frequencies.  It does not prove physiological accuracy.

The independent public-data O1/O2 SSVEP evaluation is documented in
`output/ssvep_o1o2_holdout_corrected_20260926/RESULTS.md`. It uses a 12-target
dataset whose stimulus frequencies differ from the five demonstration defaults
above. On 20 held-out subjects, the two fixed-cap-compatible channels did not
reach deployment-grade accuracy; the eight-channel dataset sanity check uses
additional occipital sites absent from the fixed Cyton cap and must not be
reported as its accuracy. No Z15 SSVEP service was changed by this experiment.

## Emotion baseline

Run the single-session, leave-one-complete-trial-out baseline:

```powershell
python .\eeg_apps_z15\emotion_baseline.py
```

The generated metrics, raw predictions and a JSON export of the scaler and LDA
parameters are written to `eeg_apps_z15/output/emotion_baseline`.  This is a
functional baseline on one participant/session, not cross-participant evidence.

### GAMEEMO 14-to-8-channel cross-participant baseline

The official GAMEEMO v3 archive is stored at
`D:\ican\datasets\GAMEEMO\GAMEEMO_v3.zip`; the complete short-path extraction
is in `D:\ican\datasets\GAMEEMO\data`. Run:

```powershell
python .\eeg_apps_z15\gameemo_8ch_baseline.py
```

This performs participant-wise leave-one-subject-out evaluation under identical
14-channel and fixed 8-channel conditions. It writes a dataset manifest, raw
predictions, metrics and an ARM-oriented JSON model to
`eeg_apps_z15/output/gameemo_8ch`. The exported model remains a prototype until
Cyton domain shift and personal calibration are measured.

### Contact-corruption robustness and SQI gating

Run `python .\eeg_apps_z15\gameemo_contact_robustness.py` after the clean
baseline. It tests dropout, flatline, broadband noise, 50 Hz interference,
drift, bursts, clipping, composite poor contact and channel swapping at three
severities and three seeds. It compares plain inference, the current 100-uV
gate, adaptive multi-descriptor SQI gating and an oracle corruption mask under
the same participant-wise folds. Results go to
`output/gameemo_contact_robustness`.

Already clipped samples are not reconstructed. The safe response is to
downweight that channel, continue with the remaining channels and expose low
confidence to the user interface.

The completed three-seed result and its limitations are summarized in
`CONTACT_ROBUSTNESS_RESULTS.md`. On the five severe contact-relevant conditions,
mask augmentation plus adaptive SQI improved mean balanced accuracy from 29.57%
to 33.62%, while clean balanced accuracy changed from 36.88% to 36.46%.

## Planned hardware split

- PC display or Z15 HDMI: frame-synchronised visual stimulation.
- Cyton + USB dongle: 8-channel acquisition at 250 Hz.
- Z15 ARM first version: filtering, CCA, confidence/rejection, logging and web
  API.
- PL acceleration: considered only after ARM profiling shows a useful target.

CCA is small, so an ARM-only baseline is the correct first deployment.  Moving
it to PL before real-data validation would add implementation risk without
establishing a useful speedup claim.

## Data still required

Update 2026-09-26: the complete SEED Preprocessed_EEG set is now available at
`D:\ican\datasets\SEED\SEED\Preprocessed_EEG` (45 recordings). The historical
missing-SEED note below no longer describes the current data inventory.
The fixed-eight-channel deployed-gate LOSO audit is in
`output/seed_gated_evaluation_20260926/RESULTS.md`. It failed the frozen
accuracy/coverage retention criteria; this experiment did not change the board.
The follow-up fixed-policy comparison is in
`output/seed_gate_policy_comparison_20260926/RESULTS.md`: conditional short-gap
baseline retention improved simulated interruption recovery, but soft-warning
inference with frozen adaptation failed the clean accuracy noninferiority check.
Neither policy was deployed by this experiment.
Follow-up: `output/seed_warning_update_ablation_20260926/RESULTS.md` isolates
warning-window mean updates and recovers clean balanced accuracy to 67.40%
(not a significant gain over the original 67.32%).
`output/cyton_short_gap_replay_20260926/RESULTS.md` records isolated PC/ARM parity;
the existing real recording was ineligible for baseline retention, while the
explicitly synthetic positive control recovered in 14 seconds. No live policy changed.

- Emotion: the complete SEED/SEED-IV data that produced `merged.csv`, plus the
  participant/session manifest.  The current folder has only one 62-channel,
  15-trial recording and no `merged.csv` or checkpoint.
- SSVEP: labelled Cyton trials containing stimulus ID, actual display onset and
  end timestamps, channel map, sample counter and packet-loss information.

See `SOURCE_AUDIT.md` for the detailed findings and the acceptance gates.

## O1/O2 causal SSVEP candidate (2026-09-26)

The current fixed cap remains `F3,F4,C3,C4,T7,T8,O1,O2`. The isolated
`ssvep_stream.py` reads raw O1/O2 only, retains causal filter state across
10-sample batches, emits a 2-second candidate every 200 ms, and clears stale
results on discontinuity or disconnect. It does not send actuator commands,
use PL, change the live UI, or replace the emotion/fatigue processing path.

The frozen unseen-subject evaluation (Wang2016 S21–S35) and PC/ARM replay
artifacts are in `output/ssvep_causal_20260926/RESULTS.md`. Causal accuracy was
80.56% versus 81.39% for the same-subject offline baseline; this is four-target
public-data performance, not Cyton accuracy. The completed accelerated ARM
replay passed numerical parity. The first paced attempt lost SSH connectivity;
its audit is preserved in `board_audit_paced_interrupted_20260926.json`.
On 2026-09-27 the old remote result directory was confirmed empty with no replay
process, then one isolated rerun completed: 144 seconds, 3,600 batches, 408
decisions, with PC/ARM numerical parity and unchanged production snapshots.
Completion lateness was p95 20.16 ms, max 286.78 ms, final 2.08 ms; five batches
exceeded 200 ms. This supports recorded-replay catch-up, not a hard-real-time or
full-live-load guarantee. See `arm_paced/report.json` and `board_audit_paced.json`.
Next is a quality/event-aware shadow interface; no live SSVEP control is enabled.

Update 2026-09-27: that observation-only packet interface is now deployed.
`pynq_guardianloop/ssvep_shadow.py` consumes raw O1/O2 before the primary
prefilter and PL quantization. Packet/clock discontinuities clear the candidate;
fresh input must warm up again. The UI has a separate `/api/ssvep-shadow` card,
with stale-frequency hiding and explicitly separate historical replay.
No actuator commands or personal-calibration claims are enabled.

Update 2026-09-30: a separate `/ssvep-cued` page and
`pynq_guardianloop/ssvep_cued.py` now pair a manually started single-frequency
browser cue with the existing live O1/O2 shadow candidate. A 2.5-second
post-presentation guard, three adjacent matching 200 ms windows, fresh/live
source, O1/O2 SQI, and browser-reported frame health are required for a
display-only match. Rest trials never accept a frequency. The original passive
shadow remains unchanged; neither the PL nor the acquisition service was
modified. Local regression and a no-flicker rest-session HTTP check on Z15
passed. With Cyton off, no real gaze classification was tested, and browser
frame reports do not establish optical frequency or no-target false-trigger
rate. See `pynq_guardianloop/DEPLOYMENT.md` for operation and rollback.

The cued trial now writes a private, append-only JSONL audit of presentation
receipts, browser-frame health, polled shadow windows, interlock decisions and
trial ends. Board monotonic time plus boot ID, not the unsynchronized wall clock,
is the within-boot timing basis. Polling can miss intermediate shadow windows.
`verify_ssvep_cued_replay.py` checks recorded rejection and separately fabricated
state transitions; its report is `output/ssvep_cued_audit_20260930/report.json`.
Neither check validates optical flicker timing or real gaze accuracy.
The 2026-09-30 non-flashing browser timing preflight is recorded in
`output/ssvep_display_preflight_20260930/RESULTS.md`; its 60 Hz callback-grid
simulation is not a photodiode measurement and is display-specific.

See `output/ssvep_shadow_20260927/RESULTS.md` for preserved failed checks,
the false-warmup bug fix, full-loop output parity, engineering quality thresholds,
90-second paced-reader replay, installed hashes, and rollback commands.
Models, production SQI module and bitstream are unchanged. A synthetic accelerated
stress trace still showed a 4.16-second simulated backlog peak; this is not a
hard-real-time guarantee. The 90-second paced recorded trace consumed all 22,500
packets, with snapshot input age p95 410 ms and maximum 675 ms.

```powershell
python -m unittest discover -s . -p 'test_ssvep*.py'
python ssvep_causal_evaluate.py --output output/ssvep_causal_20260926
python run_ssvep_causal_board_replay.py --output output/ssvep_causal_20260926
python run_ssvep_causal_board_replay.py --output output/ssvep_causal_20260926 --paced
python report_ssvep_causal.py --output output/ssvep_causal_20260926
```

### Asynchronous SSVEP experiment — not deployed (2026-09-27)

The bounded process candidate in `pynq_guardianloop/ssvep_async.py` was tested
in an isolated board directory against the same paced Cyton recording. Primary
outputs matched and packet-processing p99 improved, but combined acceptance
failed: final snapshot input-age p95 was 940ms and SSVEP input skips were 2.05%.
No production files, models, thresholds, bitstream or services were changed.
The local acquisition entry point is an **unreleased candidate**, not a file to
copy wholesale to the board. See `output/ssvep_async_20260927/RESULTS.md` and
`audit.json`; all failed attempts are preserved. `deploy_ssvep_async.py` refuses
promotion without passing both the performance gate and primary parity checks.

### Fixed-reference/SQI cache experiment — not deployed (2026-09-27)

The next isolated candidate caches fixed CCA references, reuses EEG whitening,
computes only needed SSVEP SQI columns, and stores a compact raw O1/O2 ring.
Historical replay produced 392 identical decisions and scores (maximum error 0).
The final full-loop paced run reduced total CPU time by 13.66%, but snapshot
input-age p95 was 715.63 ms, failing the frozen 500 ms gate. The earlier cache
version passed freshness but missed the 10% CPU gate; both results are retained.
The cached asynchronous candidate also failed freshness. No production files,
models, quality thresholds or PL configuration were replaced. Local cache and
async sources remain unreleased candidates, not a wholesale deployment bundle.
See `output/ssvep_cache_20260927/RESULTS.md`, `audit.json` and
`matrix_before_ring/` for exact scope, negative results and reproduction details.

### Long-stall diagnosis (2026-09-27)

Optional replay instrumentation now separates stage wall time from thread CPU,
captures slow packet IDs, and supports a waveform-output ablation plus primary
status/telemetry on tmpfs. Four isolated runs retained exact primary outputs;
longest pauses were mostly non-CPU time. Disabling waveform output and matching
production primary storage did not remove the tail in single exploratory runs.
After replay stopped, 60 passive production snapshots had input-age p95 232 ms
and maximum 923 ms, with no restart during that minute. The broader experiment
did observe an automatic restart after `Cyton serial reader stopped`; current
reader code discards the underlying OSError/queue.Full distinction. Next priority
is bounded reader-error reporting and injected recovery checks, not changing
classifiers based on these pauses. No production source or model was modified.
Evidence and limitations: `output/stall_trace_20260927/RESULTS.md` and `summary.json`.

### Cyton serial-reader failure reporting (2026-09-27)

The Z15 acquisition entry point now distinguishes serial I/O error, packet
queue overflow, repeated EOF, silence timeout and unexpected reader-process
exit, logs counts without raw EEG, invalidates stale primary status, then lets
systemd restart it. Board-side pipe tests and full-main injected faults passed;
healthy replay preserved primary output. One real post-deployment incident
reported `queue_full` and was automatically restarted. This identifies that
failure category but does not solve the processing backlog that caused it.
After the final promotion, a 60-second read-only check saw a second real
`queue_full` restart and snapshot input age up to 81.75 seconds. Automatic
restart is verified; stable live operation is not. Do not present this as
a solved real-time pipeline.
Only `cyton_guardianloop.py` was promoted, with backups; model/PL hashes remain
unchanged. See `output/reader_crash_final_20260927/RESULTS.md` and
`deployment.json` for evidence and rollback locations.

### Fixed-cap motor imagery offline gate (2026-09-30)

PhysioNet EEGMMIDB runs 4/8/12 were downloaded with official SHA-256 checks,
using the unchanged `F3,F4,C3,C4,T7,T8,O1,O2` cap. The preregistered
subject-disjoint lightweight classifier failed its promotion gate: selected
C3/C4 model scored 0.533 mean balanced accuracy on 20 test participants.
Several development-only alternatives did not reach 0.60. MI remains absent
from the production service; no bitstream or Z15 runtime was changed. See
`output/mi_physionet_fixed8_v1/RESULTS.md` and the raw JSON artifacts.

### Causal spatial MI development — not promoted (2026-10-01)

Real-wearing acceptance is postponed at the user's request. A bounded,
preregistered four-method comparison used the fixed cap and 267 verified EDFs
from S001-S089 only. The selected FBCSP-LDA scored 0.5652 mean participant
balanced accuracy in cross-person development and 0.5866 after labeled personal
calibration, evaluated on a later run. Neither met its preset continuation
threshold. These are development results, not new blind-test or Cyton accuracy.
The C3/C4 diagonal-power comparator also uses the eight-channel trace denominator;
it must not be described as a standalone two-electrode system.

Eight MI math/guard tests passed. A read-only, in-memory ARM component check
matched all 867 precomputed-covariance classifications (max score error
8.88e-16); its roughly 1ms timing excludes filtering, covariance extraction,
quality checks and live acquisition. Protected release/boot hashes were
unchanged. No MI service, control output or PL accelerator was enabled.
See `MI_SPATIAL_DEV_PLAN.md`, `output/mi_spatial_dev_20261001/RESULTS.md`,
`development.json` and `component_audit.json`. The next data-source audit is
documented in `MI_CHO2017_NEXT_DATA.md`; that note preserves the initial
not-yet-downloaded state and the later raw-data audit. More trials do not
guarantee higher accuracy.

### Cho2017 fixed-eight causal development (2026-10-01)

The raw-data reader preserves author trial order, selects only the unchanged
fixed eight electrodes, and extracts a causal 0.5–2.5s window from independent
original 7s epochs. It does not concatenate classes into a synthetic continuous
session, mix actual movement with imagery, or discard author-flagged trials
silently. The original GigaDB readme states CC0 (unless specified otherwise),
distinct from the maintained loader's CC-BY metadata. Raw downloads are under
`D:\ican\datasets\Cho2017`, verified against object length and remote ETag;
locally computed SHA-256 is provenance, not an author-published SHA-256.

The locked `cho2017_protocol.json` contains 30 training, 10 development and
12 confirmation participants. Three fixed lightweight methods compare
zero-calibration cross-person use with a separately reported first-60-labeled-
trial personal calibration. Confirmation is conditional and once-only; no
automatic promotion or control output is allowed. Seventeen reader/causality/MI
math tests passed. See `MI_CHO2017_PLAN.md` and
`output/cho2017_source_audit_20261001/RESULTS.md`. This candidate has not been
installed on Z15 and does not change the frozen release.

The completed 40-person run retained 8,080 trials, including 644 author-flagged
trials. Selected CSP-LDA scored 0.5975 cross-person development BA and 0.6050
after 60 labeled personal trials; neither passed its locked continuation gate.
On identical later trials, the personal-minus-cross difference was -0.00286
(paired participant 95% CI [-0.08071, 0.06071]); excluding only flagged test
trials yielded 0.60384, a diagnostic rather than a new primary result.
The 12 confirmation EEGs remain unread and MI stays unpromoted. Full evidence
and reproduction commands: `output/cho2017_fixed8_dev_20261001/RESULTS.md`.

### Cho2017 training-only baseline/alignment diagnosis (2026-10-01)

Four conditions were fixed before this experiment's scores and compared on
the same 4,280 later trials in 30 original-training-person LOSO folds. All
6,080 complete trials (515 author-flagged) were retained; each held-out person's
first 60 trials were unscored for every condition. Previous 10-person development
and 12-person confirmation EEGs were not read again, and the old mixed cache
was not loaded. Prefix-only alignment uses unlabeled cued trials, not resting
SQI calibration or zero-calibration cross-person use.

CSP-LDA scored 0.59101, pre-cue log-power ratios 0.54823, aligned CSP 0.60111,
and aligned CSP plus ratios 0.60434 mean participant BA. The best paired gain
was 0.01333, with three-comparison-adjusted bootstrap CI [-0.01190, 0.03929].
None met the prelocked 0.60 absolute BA / 0.03 paired gain / positive adjusted
CI continuation rule. No candidate was exported or installed; MI control remains
disabled. These are exploratory training-selection results, not independent
confirmation or Cyton accuracy.

Thirty unit tests passed; the shared preprocessing retained byte-identical
old covariance output. A separate no-refit audit independently recomputed all
17,120 saved predictions, scores and gates (max score error 3.11e-15). Code
snapshots, fold parameters, raw-file hashes and the training-only feature cache
are saved. Frozen recovery ZIP hash was unchanged and no board operations occurred.
See `cho2017_training_diagnostic_protocol.json`,
`MI_CHO2017_TRAINING_DIAGNOSTIC_PLAN.md`, and
`output/cho2017_training_diagnostic_20261001/RESULTS.md` for reproduction.

### Current MI route — left/right imagery only (2026-10-01)

At the user's request, five-finger decoding is no longer an active development
or deployment branch. Preserve its data, code and negative results; do not
delete them or evaluate its held-out confirmation EEGs. The physical cap remains
`F3,F4,C3,C4,T7,T8,O1,O2`.

The unaugmented Cho2017 `C2_EEGNet_SMALL` remains the left/right offline
candidate (30-person training-group LOSO, three-seed mean BA 0.63828).
This is not final independent confirmation or Cyton accuracy. No MI model was
promoted or installed by this route change. Next, lock a separate once-only
confirmation protocol before reading the 12 held-out participants; ARM export
and measured PL decisions follow only after the corresponding gates.
See [MI_CURRENT_ROUTE.md](MI_CURRENT_ROUTE.md) for the current decision,
evidence paths and deployment boundaries. It supersedes historical suggestions
to continue the finger-model branch, not the historical experiment results.

### Independent12 left/right confirmation — completed, not promoted (2026-10-01)

The unaugmented EEGNet was trained with 27 original-source people and three
source-only validation people before any confirmation EEG access. The once-only
12-person evaluation retained all 2,440 original trials and scored the same
1,720 post-prefix trials for all methods. Three-seed mean person BA was 0.60694
(95% person CI [0.55476, 0.67540]), versus fixed B1 at 0.58790. The paired
gain was 0.01905 with 95% CI [-0.02500, 0.06468], failing the prelocked minimum
0.03 gain and positive paired interval. Seed42 passed its separate absolute
artifact check but cannot override the failed primary gate.

All 6,880 labels and all original trial identities were verified; CPU/GPU
labels matched, maximum logit error 4.77e-7, and 42 tests passed. No ARM export,
board timing, production service, PL or actuator change followed. These 12
people are now exposed, not an untouched confirmation set for future tuning.
See `MI_CONFIRMATION_PLAN.md`, `mi_confirmation_protocol.json`, and
`output/mi_confirmation_20261001/RESULTS.md` for the frozen evidence and limits.

### Isolated ARM compute-peak comparison (2026-10-03)

Three fixed-input 156-second replays compared the frozen synchronous baseline,
an opt-in array covariance buffer, and that buffer with the existing bounded
SEED process. The combined candidate reduced input-age p95 by 38.7% with
unchanged primary prediction payloads, but its strict SEED event-parity gate
failed on two extra invalid waiting events. No candidate was installed; live
services were restored and formal file/service/boot hashes were unchanged.
`CovarianceFeatureStream(storage="array")` and the replay-only harness flag
are unreleased candidates. Do not deploy this local directory wholesale.
See `output/ssvep_compute_peak_20261003/RESULTS.md` and `paired_run/AUDIT.json`
for the measurements, failed gates, recovery history and reproducible audit.

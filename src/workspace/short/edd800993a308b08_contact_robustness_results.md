# GAMEEMO 8-channel contact-corruption robustness result

## Frozen question

Can training-only channel masking plus training-fold calibrated SQI gating reduce
corruption-induced loss in participant-independent four-class emotion
recognition without materially reducing clean performance?

The evaluation uses 28-participant LOSO, 8,288 non-overlapping four-second
windows and three deterministic corruption seeds. Corruption is generated only
after choosing the held-out participant. Scaling, replacement medians, SQI
calibration and classifiers are fit on training participants only.

## Main result

Balanced accuracy:

- Clean plain model: **36.88%**
- Clean mask-augmented model: **36.46%** (absolute change -0.43 points)
- Mean over all 27 corrupted conditions, plain: **34.28%**
- Mean over all 27 corrupted conditions, mask augmentation + adaptive SQI:
  **34.70%** (absolute change +0.41 points)
- Mean over five severe contact-relevant conditions, plain: **29.57%**
- Mean over five severe contact-relevant conditions, mask augmentation +
  adaptive SQI: **33.62%** (absolute change +4.05 points)
- Same five conditions with the synthetic oracle mask: **33.84%**

The five severe contact-relevant results were:

| Condition | Plain | Mask augmentation + adaptive SQI | Oracle mask |
|---|---:|---:|---:|
| Flatline | 28.35% | 33.52% | 33.77% |
| 50 Hz interference | 29.95% | 33.55% | 33.68% |
| Transient burst | 28.57% | 33.79% | 34.08% |
| Hard clipping | 31.08% | 33.56% | 33.72% |
| Composite poor contact | 29.91% | 33.67% | 33.96% |

The clean-like rejection rate measured with channel swapping was **0.33%** after
training-fold quantile calibration. The severe-condition improvement was in the
same direction for seeds 13, 37 and 73.

## Interpretation

The lightweight strategy is useful when a channel is clearly unusable because
of flatlining, mains pickup, bursts, clipping or compound poor contact. It does
not recover samples discarded by clipping. It instead suppresses the bad
channel and lets a model trained with missing-channel examples use the remaining
channels.

SQI cannot reliably detect channel identity swaps because swapped EEG can have
normal amplitude and spectrum. Very slow drift may also be removed by the
4-Hz feature filter before it harms this particular classifier. These conditions
must not be used to claim universal robustness.

Synthetic results do not establish real Cyton robustness. The next validation
must replay or collect unlabeled Cyton segments with stable contact, hair
obstruction, natural loosening and brief disconnection, then compare their SQI
statistics with the synthetic protocol before deploying the gate.

## Traceable artifacts

- `output/gameemo_contact_robustness/robustness_metrics.json`
- `output/gameemo_contact_robustness/robustness_summary.csv`
- `output/gameemo_contact_robustness/predictions.csv`

The predictions file contains every seed, condition, method, participant,
recording window, target and prediction.

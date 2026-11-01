"""Descriptive diagnosis of the frozen 24-trial session; never tune on confirmation."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.signal import welch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pynq_guardianloop'))
from mi_eegnet_rms import OfflineEEGNet

DATA = ROOT / 'eeg_apps_z15/output/mi_personal_confirmation_20261003_audit2'
OUT = ROOT / 'eeg_apps_z15/output/mi_rms_live_virtual_20261003'
MODEL = ROOT / 'eeg_apps_z15/output/mi_rms_comparison_20261003/experimental_rms_eegnet.npz'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=False)
    protocol = dict(purpose='descriptive_error_diagnosis_only', tuning=False,
                    new_independent_accuracy=False, model_changed=False,
                    thresholds_changed=False, labels_swapped=False,
                    hypothesis='Check whether errors are confined to weak margins or failed hard SQI',
                    falsification='Accepted errors have margins comparable to correct trials',
                    calibration_only_personal_fit=True)
    (OUT / 'PLAN.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    frozen = json.loads((DATA / 'SHA256.json').read_text(encoding='utf-8'))
    for relative, expected in frozen.items():
        if sha(DATA / relative) != expected:
            raise ValueError('Frozen evidence changed: ' + relative)
    model = OfflineEEGNet(MODEL, allow_experimental=True)
    with np.load(DATA / 'records/personal_readout.npz', allow_pickle=False) as head:
        mean, scale, weight, bias = [head[key].copy() for key in ('mean', 'scale', 'weight', 'bias')]
    phases, waves, expected_logits = {}, [], []
    for phase in ('calibration', 'confirmation'):
        trials = json.loads((DATA / 'records' / phase / 'trials.json').read_text(encoding='utf-8'))
        rows, features = [], []
        for trial in trials:
            with np.load(DATA / 'records' / trial['array_file'], allow_pickle=False) as record:
                wave = record['filtered'].T[None]
                f = model.features(wave)[0]
                base_logits = model.score_features(f[None])[0]
                np.testing.assert_allclose(base_logits, record['source_logits'], atol=1e-10, rtol=0)
                personal_margin = float(((f - mean) / scale / np.sqrt(240)) @ weight + bias)
                base_margin = float(base_logits[1] - base_logits[0])
                freq, psd = welch(record['filtered'], fs=250, nperseg=250, axis=0)
                ratios = {}
                for name, low, high in (('mu', 8, 13), ('beta', 13, 30)):
                    band = psd[(freq >= low) & (freq < high)].sum(0)
                    ratios[name + '_C4_over_C3_log'] = float(np.log((band[3]+1e-12)/(band[2]+1e-12)))
                rows.append(dict(ordinal=trial['ordinal'], target=trial['target'], accepted=trial['accepted'],
                                 base_label=('left', 'right')[int(np.argmax(base_logits))],
                                 personal_label='right' if personal_margin > 0 else 'left',
                                 base_margin=base_margin, personal_margin=personal_margin,
                                 shared_filtered_rms_uv=float(np.sqrt(np.mean(record['filtered']**2))),
                                 conditioned_p99_uv=float(np.max(np.quantile(np.abs(record['conditioned_uv']-
                                     np.median(record['conditioned_uv'], axis=0)), .99, axis=0))),
                                 **ratios))
                features.append(f)
                waves.append(wave[0])
                expected_logits.append(base_logits)
        phases[phase] = dict(trials=rows, features=np.stack(features))
    test = phases['confirmation']['trials']
    errors = [r for r in test if r['base_label'] != r['target']]
    correct = [r for r in test if r['base_label'] == r['target']]
    cal_f = phases['calibration']['features']
    result = dict(protocol=protocol, input_manifest_sha256=sha(DATA / 'SHA256.json'),
                  model_sha256=sha(MODEL), analysis_script_sha256=sha(Path(__file__)),
                  frozen_files_checked=len(frozen), features=240, calibration_trials=12,
                  calibration_centered_rank=int(np.linalg.matrix_rank(cal_f-cal_f.mean(0))),
                  personal_calibration_correct=sum(r['personal_label']==r['target'] for r in phases['calibration']['trials']),
                  personal_confirmation_correct=sum(r['personal_label']==r['target'] for r in test),
                  base_confirmation_correct=len(correct), base_error_ordinals=[r['ordinal'] for r in errors],
                  error_absolute_margins=[abs(r['base_margin']) for r in errors],
                  correct_absolute_margin_range=[min(abs(r['base_margin']) for r in correct),
                                                 max(abs(r['base_margin']) for r in correct)],
                  personal_only_correct_ordinals=[r['ordinal'] for r in test if r['personal_label']==r['target'] and r['base_label']!=r['target']],
                  base_only_correct_ordinals=[r['ordinal'] for r in test if r['base_label']==r['target'] and r['personal_label']!=r['target']],
                  phases={key: value['trials'] for key, value in phases.items()},
                  physiological_cause_established=False, full_raw_filter_replay_verified=False,
                  decision='Keep frozen base RMS; disable personal head in new isolated virtual entry',
                  limitation='Cued intention is not physiological ground truth; rests and filter initial states were not saved')
    (OUT / 'error_diagnosis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    np.savez_compressed(OUT / 'saved_window_probes.npz', waveforms=np.stack(waves), logits=np.stack(expected_logits))
    print(json.dumps({k: result[k] for k in ('base_error_ordinals', 'error_absolute_margins',
          'correct_absolute_margin_range', 'personal_calibration_correct', 'personal_confirmation_correct',
          'calibration_centered_rank', 'personal_only_correct_ordinals', 'base_only_correct_ordinals')}, indent=2))


if __name__ == '__main__':
    main()

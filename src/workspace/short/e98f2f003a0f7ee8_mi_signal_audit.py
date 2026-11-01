"""Descriptive training-cache and synthetic-filter audit; no model fitting."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from scipy import signal

from cho2017_features import CausalEEGFilter
from cho2017_training_diagnostic import validate_protocol

HERE = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def laterality(baseline, task, labels, subjects, participants):
    baseline, task = np.asarray(baseline), np.asarray(task)
    labels, subjects = np.asarray(labels), np.asarray(subjects)
    shape = (len(labels), 7, 8)
    if baseline.shape != shape or task.shape != shape or subjects.shape != labels.shape:
        raise ValueError('Expected seven bands by eight channels for each trial')
    if not np.isfinite(baseline).all() or not np.isfinite(task).all():
        raise ValueError('Nonfinite variance; do not silently remove trials')
    if (baseline < 0).any() or (task < 0).any():
        raise ValueError('Variance cannot be negative')
    if set(np.unique(subjects)) != set(participants) or set(np.unique(labels)) != {0, 1}:
        raise ValueError('Unexpected people or labels')
    ratio = np.log(np.maximum(task, 1e-12) / np.maximum(baseline, 1e-12))
    output = []
    for band in (0, 1):
        rows = []
        for person in participants:
            selected = subjects == person
            left = selected & (labels == 0)
            right = selected & (labels == 1)
            if not left.any() or not right.any():
                raise ValueError('Both labels required for every training person')
            d = ratio[:, band, 2] - ratio[:, band, 3]
            rows.append({'subject': person, 'left_trials': int(left.sum()),
                         'right_trials': int(right.sum()),
                         'mean_left_c3_minus_c4': float(d[left].mean()),
                         'mean_right_c3_minus_c4': float(d[right].mean()),
                         'left_minus_right_contrast': float(d[left].mean() - d[right].mean())})
        contrasts = np.array([row['left_minus_right_contrast'] for row in rows])
        output.append({'band_hz': [[8, 12], [18, 26]][band],
                       'mean_person_contrast': float(contrasts.mean()),
                       'median_person_contrast': float(np.median(contrasts)),
                       'positive_person_count': int((contrasts > 0).sum()),
                       'negative_person_count': int((contrasts < 0).sum()),
                       'zero_person_count': int((contrasts == 0).sum()),
                       'per_person': rows})
    return output


def response_at(sos, frequency_hz, sample_rate=250):
    frequencies = np.array([frequency_hz - .001, frequency_hz, frequency_hz + .001])
    _, response = signal.sosfreqz(sos, worN=frequencies, fs=sample_rate)
    phase = np.unwrap(np.angle(response))
    delay = -(phase[2] - phase[0]) / (2 * np.pi * (frequencies[2] - frequencies[0]))
    return float(abs(response[1])), float(delay)


def filter_response():
    conditioning = CausalEEGFilter().sos
    up, down, source_rate = 125, 256, 512
    half = 10 * down
    fir = up * signal.firwin(2 * half + 1, 1 / down, window=('kaiser', 5))
    fir_delay = half / (source_rate * up)
    rows = []
    for band, frequency in (((8, 12), 10), ((18, 26), 22)):
        band_sos = signal.butter(4, band, fs=250, btype='bandpass', output='sos')
        gain, iir_delay = response_at(np.vstack((conditioning, band_sos)), frequency)
        _, fir_response = signal.freqz(fir, worN=[2 * np.pi * frequency / (source_rate * up)])
        combined_gain = gain * float(abs(fir_response[0])) / up
        rows.append({'band_hz': list(band), 'frequency_hz': frequency,
                     'gain_db': float(20 * np.log10(combined_gain)),
                     'iir_group_delay_s': iir_delay, 'resampler_group_delay_s': fir_delay,
                     'total_group_delay_s': iir_delay + fir_delay})
    return {'sample_rate_hz': 250, 'conditioning_sos': conditioning.tolist(),
            'points': rows,
            'interpretation': 'Small-signal steady-state group delay, not a constant latency, neural onset, or a reason to shift EEG into future data'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'output/mi_literature_signal_audit_20261001')
    args = parser.parse_args()
    protocol_path = HERE / 'mi_signal_audit_protocol.json'
    protocol = read_json(protocol_path)
    original = read_json(HERE / 'cho2017_protocol.json')
    training = read_json(HERE / protocol['training_protocol'])
    allowed = validate_protocol(original, training)
    if protocol['channels'] != original['channels'] or protocol['bands'] != [[8, 12], [18, 26]]:
        raise ValueError('Audit montage and bands changed')
    cache = HERE / protocol['cache']
    expected_cache = HERE / 'output/cho2017_training_diagnostic_20261001/training_statistics.npz'
    if cache.resolve() != expected_cache.resolve():
        raise ValueError('Only the original training-only cache is allowed')
    source_provenance = read_json(cache.parent / 'provenance.json')
    if (source_provenance['subjects_actually_read'] != allowed
            or source_provenance['former_development_eeg_read']
            or source_provenance['confirmation_eeg_read']
            or source_provenance['old_mixed_feature_cache_loaded']):
        raise ValueError('Cache provenance violates training-only scope')
    manifest = read_json(cache.parent / 'trial_manifest.json')
    if len(manifest) != 6080 or set(row['subject'] for row in manifest) != set(allowed):
        raise ValueError('Unexpected manifest population')
    with np.load(cache, allow_pickle=False) as statistics:
        labels, subjects = statistics['labels'], statistics['subjects']
        if labels.tolist() != [row['label'] for row in manifest] or subjects.tolist() != [row['subject'] for row in manifest]:
            raise ValueError('Cache/manifest row identities differ')
        contrasts = laterality(statistics['baseline_variance'], statistics['task_variance'], labels, subjects, allowed)
    report = {'scope': 'Training-only descriptive physiology proxy plus synthetic filter response; not a new classifier',
              'created_at_local': datetime.now().isoformat(), 'protocol': protocol,
              'people': allowed, 'trials': len(manifest),
              'author_flagged_trials_retained': sum(row['voltage_bad'] or row['emg_bad'] for row in manifest),
              'cue_sample_counts': {str(cue): sum(row['cue_sample'] == cue for row in manifest)
                                    for cue in sorted(set(row['cue_sample'] for row in manifest))},
              'c3_c4_contrasts': contrasts, 'filter_response': filter_response(),
              'raw_eeg_read_this_run': False, 'former_development_eeg_read': False,
              'confirmation_eeg_read': False, 'classifier_fitted': False,
              'trials_discarded': 0, 'board_accessed': False,
              'promotion_gate_passed': False, 'control_enabled': False}
    paths = [Path(__file__), protocol_path, HERE / 'test_mi_signal_audit.py',
             HERE / 'cho2017_protocol.json', HERE / 'cho2017_training_diagnostic_protocol.json',
             HERE / 'cho2017_features.py', HERE.parent / 'pynq_guardianloop/cyton_sqi.py',
             cache, cache.parent / 'trial_manifest.json', cache.parent / 'provenance.json']
    report['sha256'] = {str(path): sha256(path) for path in paths}
    args.output.mkdir(parents=True, exist_ok=False)
    snapshot = args.output / 'audit_code_snapshot'
    snapshot.mkdir()
    for path in paths[:7]:
        shutil.copy2(path, snapshot / path.name)
    (args.output / 'signal_audit.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('trials', 'author_flagged_trials_retained', 'cue_sample_counts',
                                                 'c3_c4_contrasts', 'filter_response')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

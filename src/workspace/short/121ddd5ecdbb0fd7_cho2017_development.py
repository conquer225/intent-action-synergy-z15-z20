"""Bounded locked-protocol Cho development; deliberately refuses confirmation IDs."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time

import numpy as np
import scipy
import sklearn

from cho2017_data import DATA, load_subject, hashes
from cho2017_features import trial_covariances
from mi_spatial_development import fit, predict, metrics, METHODS, BANDS
from mi_physionet_evaluate import bootstrap_ci

HERE = Path(__file__).resolve().parent


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def summarize(rows, seed):
    values = [r['balanced_accuracy'] for r in rows]
    return {'mean_subject_balanced_accuracy': float(np.mean(values)),
            'mean_subject_macro_f1': float(np.mean([r['macro_f1'] for r in rows])),
            'subject_bootstrap_95_ci': bootstrap_ci(values, seed), 'per_subject': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DATA)
    parser.add_argument('--output', type=Path, default=HERE / 'output/cho2017_fixed8_dev_20261001')
    parser.add_argument('--wait-for-data-seconds', type=int, default=0,
                        help='Bounded wait for already running downloads; never downloads or substitutes people')
    args = parser.parse_args()
    if args.wait_for_data_seconds < 0:
        raise ValueError('Non-negative bounded data wait required')
    protocol_path = HERE / 'cho2017_protocol.json'
    protocol = json.loads(protocol_path.read_text())
    if protocol['bands_hz'] != [list(band) for band in BANDS] or any(
            protocol['band_indices'][method] != METHODS[method][0] for method in protocol['band_indices']):
        raise ValueError('Locked protocol and reused feature indices disagree')
    args.output.mkdir(parents=True, exist_ok=False)
    subjects_to_read = sorted(protocol['train_subjects'] + protocol['development_subjects'])
    assert set(subjects_to_read).isdisjoint(protocol['confirmation_subjects'])
    paths = [Path(__file__), protocol_path, HERE / 'MI_CHO2017_PLAN.md', HERE / 'cho2017_data.py',
             HERE / 'cho2017_features.py', HERE / 'mi_spatial_development.py',
             HERE.parent / 'pynq_guardianloop/mi_spatial.py', HERE.parent / 'pynq_guardianloop/cyton_sqi.py']
    save(args.output / 'provenance.json', {'started_at_local': datetime.now().isoformat(),
         'protocol_sha256': hashes(protocol_path)['sha256'], 'subjects_to_read': subjects_to_read,
         'maximum_data_wait_seconds': args.wait_for_data_seconds,
         'confirmation_subjects_read': False, 'channels': protocol['channels'],
         'source_code_sha256': {str(p): hashes(p)['sha256'] for p in paths},
         'source_document_sha256': {name: hashes(args.root / 'source_docs' / name)['sha256']
             for name in ('readme.txt', 'readme_100295.txt', 'trial_sequence.zip',
                          'moabb_gigadb_reference.py', 'gigadb_object_listing.xml', 'author_fulltext.xml')},
         'software': {'numpy': np.__version__, 'scipy': scipy.__version__, 'sklearn': sklearn.__version__}})
    parts, manifest, source_hashes = [], [], {}
    wait_used = 0.0
    for person in subjects_to_read:
        path = args.root / f's{person:02d}.mat'
        if not path.exists() and args.wait_for_data_seconds:
            print('WAITING_FOR_VERIFIED_DATA', person, flush=True)
            started = time.monotonic()
            while not path.exists():
                if wait_used + time.monotonic() - started >= args.wait_for_data_seconds:
                    raise TimeoutError(f'Data not ready: {path}; no subject skipped')
                time.sleep(1)
            wait_used += time.monotonic() - started
        item = load_subject(person, args.root)
        covs = np.stack([trial_covariances(samples, item.cue_sample, protocol) for samples in item.samples])
        parts.append(covs)
        for i in range(len(item.labels)):
            manifest.append({'subject': person, 'label': int(item.labels[i]), 'original_order': i,
                             'original_sequence_key': int(item.original_keys[i]),
                             'class_trial_index_one_based': int(item.class_trial_indices[i]) + 1,
                             'voltage_bad': bool(item.voltage_bad[i]), 'emg_bad': bool(item.emg_bad[i]),
                             'cue_sample': item.cue_sample})
        source_hashes[f's{person:02d}.mat'] = hashes(args.root / f's{person:02d}.mat')['sha256']
        print('EXTRACTED', person, len(item.labels), flush=True)
    covs = np.concatenate(parts)
    labels = np.array([r['label'] for r in manifest])
    subjects = np.array([r['subject'] for r in manifest])
    order = np.array([r['original_order'] for r in manifest])
    np.savez_compressed(args.output / 'trial_covariances.npz', covariances=covs, labels=labels,
                        subjects=subjects, order=order)
    save(args.output / 'trial_manifest.json', manifest)
    save(args.output / 'source_sha256.json', source_hashes)
    training = np.isin(subjects, protocol['train_subjects'])
    development = np.isin(subjects, protocol['development_subjects'])
    cross, personal, predictions, fitted = {}, {}, {}, {}
    for method in ('eight_power', 'CSP_LDA', 'FBCSP_LDA'):
        fitted[method] = fit(covs[training], labels[training], method)
        p, scores, err = predict(covs[development], method, fitted[method])
        cross[method] = {**metrics(labels[development], p, subjects[development]),
                         'portable_max_abs_error': err}
        predictions[method] = {'cross': [dict(manifest[i], prediction=int(v), score=float(s))
                                        for i, v, s in zip(np.flatnonzero(development), p, scores)], 'personal': []}
        rows = []
        for person in subjects_to_read:
            calibration = (subjects == person) & (order < protocol['personal_calibration']['first_chronological_trials'])
            later = (subjects == person) & ~calibration
            assert not np.any(calibration & later)
            local = fit(covs[calibration], labels[calibration], method)
            p, s, e = predict(covs[later], method, local)
            row = metrics(labels[later], p, subjects[later])['per_subject'][0]
            row.update(calibration_trials=int(calibration.sum()), portable_max_abs_error=e)
            rows.append(row)
            predictions[method]['personal'].extend([dict(manifest[i], prediction=int(v), score=float(score))
                                                   for i, v, score in zip(np.flatnonzero(later), p, s)])
        personal[method] = {group: summarize([r for r in rows if r['subject'] in protocol[key]], protocol['seed'])
                            for group, key in (('selection_train', 'train_subjects'), ('development', 'development_subjects'))}
        print('METHOD', method, 'cross', cross[method]['mean_subject_balanced_accuracy'],
              'calibrated_development', personal[method]['development']['mean_subject_balanced_accuracy'], flush=True)
    selected_cross = max(cross, key=lambda name: cross[name]['mean_subject_balanced_accuracy'])
    selected_personal = max(personal, key=lambda name: personal[name]['selection_train']['mean_subject_balanced_accuracy'])
    chosen_cross = cross[selected_cross]
    chosen_personal = personal[selected_personal]['development']
    report = {'scope': 'development, no confirmation extraction or Cyton validation', 'protocol': protocol,
              'cross': cross, 'personal_calibrated': personal, 'selected_cross': selected_cross,
              'selected_personal_on_train': selected_personal,
              'cross_continue': bool(chosen_cross['mean_subject_balanced_accuracy'] >= protocol['cross_continue']['mean_development_ba_at_least']
                                     and chosen_cross['subject_bootstrap_95_ci'][0] > protocol['cross_continue']['ci_lower_greater_than']),
              'personal_continue': bool(chosen_personal['mean_subject_balanced_accuracy'] >= protocol['personal_continue']['mean_development_ba_at_least']
                                        and chosen_personal['subject_bootstrap_95_ci'][0] > protocol['personal_continue']['ci_lower_greater_than']),
              'confirmation_subjects_read': False, 'promotion_gate_passed': False, 'control_enabled': False,
              'participants_retained': len(subjects_to_read), 'trials_retained': len(labels), 'trials_discarded': 0,
              'trial_counts': {'train': int(training.sum()), 'development': int(development.sum())},
              'author_flagged_trials_retained': sum(r['voltage_bad'] or r['emg_bad'] for r in manifest)}
    save(args.output / 'development.json', report)
    save(args.output / 'predictions.json', predictions)
    filters, scaler, lda = fitted[selected_cross]
    metadata = {'protocol_sha256': hashes(protocol_path)['sha256'], 'status': 'development_only',
                'channels': protocol['channels'], 'window_samples': 500, 'sample_rate_hz': 250,
                'epoch_after_cue_s': [.5, 2.5], 'method': selected_cross,
                'bands_hz': [protocol['bands_hz'][i] for i in METHODS[selected_cross][0]],
                'promotion_gate_passed': False, 'control_enabled': False, 'reference': 'fixed-eight common average'}
    np.savez(args.output / 'cross_development_model.npz', filters=filters, mean=scaler.mean_,
             scale=scaler.scale_, coef=lda.coef_[0], intercept=lda.intercept_[0], metadata=json.dumps(metadata))
    print(json.dumps({k: report[k] for k in ('selected_cross', 'selected_personal_on_train', 'cross_continue',
                     'personal_continue', 'participants_retained', 'trials_retained')}, indent=2), flush=True)


if __name__ == '__main__':
    main()

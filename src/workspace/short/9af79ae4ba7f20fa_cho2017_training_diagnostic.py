"""Four locked conditions, original training people only; never a board deployment."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import time

import numpy as np
import scipy
import sklearn
from threadpoolctl import threadpool_info, threadpool_limits

from cho2017_adaptation import METHODS, PREFIX_TRIALS, alignment_reference, align_covariances, log_power_ratio, fit, predict
from cho2017_data import DATA, FIXED, load_subject, hashes
from cho2017_features import trial_statistics
from mi_physionet_evaluate import bootstrap_ci, subject_metrics
from mi_spatial_development import BANDS

HERE = Path(__file__).resolve().parent


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def validate_protocol(original, diagnostic):
    allowed = diagnostic['participants']
    forbidden = diagnostic['forbidden_eeg_participants']
    if allowed != original['train_subjects'] or len(set(allowed)) != 30:
        raise ValueError('Only the original 30 training people may be read')
    if set(forbidden) != set(original['development_subjects'] + original['confirmation_subjects']):
        raise ValueError('Every previous development and confirmation person must be forbidden')
    if set(allowed) & set(forbidden) or set(allowed + forbidden) != set(range(1, 53)):
        raise ValueError('Participant isolation failed')
    if original['channels'] != list(FIXED) or diagnostic['channels'] != list(FIXED):
        raise ValueError('Fixed eight physical positions required')
    if original['bands_hz'] != [list(band) for band in BANDS] or diagnostic['methods'] != list(METHODS):
        raise ValueError('The four conditions and bands are frozen')
    if diagnostic['csp_components'] != 4 or diagnostic['csp_shrinkage'] != .1:
        raise ValueError('CSP parameters disagree with the reused implementation')
    if original['personal_calibration']['first_chronological_trials'] != PREFIX_TRIALS:
        raise ValueError('Calibration prefix is fixed at 60 original trials')
    return allowed


def read_training_person(person, root, allowed):
    if person not in allowed:
        raise ValueError('Forbidden EEG participant; no file opened')
    return load_subject(person, root)


def paired_comparison(candidate, baseline, seed):
    if [r['subject'] for r in candidate] != [r['subject'] for r in baseline]:
        raise ValueError('Paired participants disagree')
    differences = np.array([a['balanced_accuracy'] - b['balanced_accuracy']
                            for a, b in zip(candidate, baseline)])
    rng = np.random.default_rng(seed)
    boot = differences[rng.integers(0, len(differences), size=(10000, len(differences)))].mean(axis=1)
    return {'mean_ba_gain': float(differences.mean()),
            'paired_bootstrap_95_ci': np.quantile(boot, [.025, .975]).tolist(),
            'three_comparison_adjusted_98_3333_ci': np.quantile(boot, [.05 / 6, 1 - .05 / 6]).tolist(),
            'participants_improved': int((differences > 0).sum()),
            'participants_declined': int((differences < 0).sum()),
            'participants_tied': int((differences == 0).sum()),
            'per_subject_gain': [dict(subject=row['subject'], ba_gain=float(delta))
                                 for row, delta in zip(candidate, differences)]}


def passes_gate(summary, comparison, gate):
    return bool(summary['mean_subject_balanced_accuracy'] >= gate['absolute_mean_ba_at_least']
                and comparison['mean_ba_gain'] >= gate['paired_mean_gain_at_least']
                and comparison['three_comparison_adjusted_98_3333_ci'][0] > gate['family_adjusted_paired_ci_lower_greater_than'])


def save_fitted(path, fitted, metadata):
    np.savez_compressed(path, filters=fitted.filters, mean=fitted.scaler.mean_, scale=fitted.scaler.scale_,
                        coef=fitted.classifier.coef_[0], intercept=fitted.classifier.intercept_[0],
                        metadata=json.dumps(metadata, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DATA)
    parser.add_argument('--output', type=Path, default=HERE / 'output/cho2017_training_diagnostic_20261001')
    args = parser.parse_args()
    original_path = HERE / 'cho2017_protocol.json'
    diagnostic_path = HERE / 'cho2017_training_diagnostic_protocol.json'
    original = json.loads(original_path.read_text(encoding='utf-8'))
    diagnostic = json.loads(diagnostic_path.read_text(encoding='utf-8'))
    allowed = validate_protocol(original, diagnostic)
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), original_path, diagnostic_path, HERE / 'MI_CHO2017_TRAINING_DIAGNOSTIC_PLAN.md',
             HERE / 'cho2017_data.py', HERE / 'cho2017_features.py', HERE / 'cho2017_adaptation.py',
             HERE / 'test_cho2017_adaptation.py', HERE / 'test_cho2017_pipeline.py',
             HERE / 'mi_spatial_development.py', HERE / 'mi_physionet_evaluate.py',
             HERE.parent / 'pynq_guardianloop/mi_spatial.py', HERE.parent / 'pynq_guardianloop/cyton_sqi.py']
    snapshot = args.output / 'code_snapshot'
    snapshot.mkdir()
    for path in paths:
        shutil.copy2(path, snapshot / path.name)
    provenance = {'started_at_local': datetime.now().isoformat(), 'subjects_to_read': allowed,
                  'subjects_actually_read': [], 'former_development_eeg_read': False, 'confirmation_eeg_read': False,
                  'old_mixed_feature_cache_loaded': False, 'source_code_sha256': {str(p): hashes(p)['sha256'] for p in paths},
                  'source_document_sha256': {name: hashes(args.root / 'source_docs' / name)['sha256']
                      for name in ('readme.txt', 'readme_100295.txt', 'trial_sequence.zip',
                                   'moabb_gigadb_reference.py', 'gigadb_object_listing.xml', 'author_fulltext.xml')},
                  'software': {'numpy': np.__version__, 'scipy': scipy.__version__, 'sklearn': sklearn.__version__},
                  'compute_device': 'Windows PC; not ARM or PL timing', 'blas_threads': 1}
    save(args.output / 'provenance.json', provenance)
    started = time.monotonic()
    covariances, baseline_variances, task_variances, manifest, source_hashes = [], [], [], [], {}
    for person in allowed:
        item = read_training_person(person, args.root, allowed)
        statistics = [trial_statistics(samples, item.cue_sample, original) for samples in item.samples]
        covariances.append(np.stack([s[0] for s in statistics]))
        baseline_variances.append(np.stack([s[1] for s in statistics]))
        task_variances.append(np.stack([s[2] for s in statistics]))
        for i, label in enumerate(item.labels):
            manifest.append({'subject': person, 'label': int(label), 'original_order': i,
                             'original_sequence_key': int(item.original_keys[i]),
                             'class_trial_index_one_based': int(item.class_trial_indices[i]) + 1,
                             'voltage_bad': bool(item.voltage_bad[i]), 'emg_bad': bool(item.emg_bad[i]),
                             'cue_sample': item.cue_sample})
        source_hashes[f's{person:02d}.mat'] = hashes(args.root / f's{person:02d}.mat')['sha256']
        provenance['subjects_actually_read'].append(person)
        save(args.output / 'provenance.json', provenance)
        print('EXTRACTED_TRAIN_ONLY', person, len(item.labels), flush=True)
    covs = np.concatenate(covariances)
    baseline = np.concatenate(baseline_variances)
    task = np.concatenate(task_variances)
    ratios = log_power_ratio(baseline, task)
    labels = np.array([r['label'] for r in manifest])
    subjects = np.array([r['subject'] for r in manifest])
    order = np.array([r['original_order'] for r in manifest])
    np.savez_compressed(args.output / 'training_statistics.npz', covariances=covs, baseline_variance=baseline,
                        task_variance=task, log_power_ratio=ratios, labels=labels, subjects=subjects, order=order)
    save(args.output / 'trial_manifest.json', manifest)
    save(args.output / 'source_sha256.json', source_hashes)
    extraction_seconds = time.monotonic() - started

    aligned = covs.copy()
    references, whitenings = [], []
    for person in allowed:
        selected = subjects == person
        reference, whitening = alignment_reference(covs[selected, 2], order[selected])
        aligned[selected, 2] = align_covariances(covs[selected, 2], whitening)
        references.append(reference)
        whitenings.append(whitening)
    np.savez_compressed(args.output / 'prefix_only_references.npz', subjects=np.array(allowed),
                        regularized_reference=np.stack(references), whitening=np.stack(whitenings), prefix_trials=PREFIX_TRIALS)
    (args.output / 'fold_parameters').mkdir()
    predictions, fold_rows, fit_seconds = {m: [] for m in METHODS}, {m: [] for m in METHODS}, 0.0
    with threadpool_limits(limits=1):
        provenance['threadpool_info'] = threadpool_info()
        for person in allowed:
            source = subjects != person
            later = (subjects == person) & (order >= PREFIX_TRIALS)
            if set(subjects[source]) != set(allowed) - {person} or not later.any():
                raise ValueError('LOSO source/target isolation failed')
            for method in METHODS:
                values = aligned if method.startswith('EA_') else covs
                start_fit = time.monotonic()
                fitted = fit(values[source], ratios[source], labels[source], method)
                predicted, scores, error = predict(values[later], ratios[later], fitted)
                fit_seconds += time.monotonic() - start_fit
                row = subject_metrics(labels[later], predicted, subjects[later])[0]
                row.update(source_subjects=sorted(set(int(p) for p in subjects[source])),
                           source_trials=int(source.sum()), held_out_unscored_prefix_trials=PREFIX_TRIALS,
                           portable_max_abs_error=error, feature_dimensions=len(fitted.scaler.mean_))
                fold_rows[method].append(row)
                predictions[method].extend([dict(manifest[i], prediction=int(p), score=float(s))
                                           for i, p, s in zip(np.flatnonzero(later), predicted, scores)])
                save_fitted(args.output / f'fold_parameters/s{person:02d}_{method}.npz', fitted,
                            {'method': method, 'source_subjects': row['source_subjects'], 'held_out_subject': person,
                             'target_labels_used_for_fit': False, 'control_enabled': False,
                             'covariance_alignment': 'own first60 original-order unlabeled trials, frozen' if method.startswith('EA_') else None})
            print('LOSO', person, {m: round(fold_rows[m][-1]['balanced_accuracy'], 4) for m in METHODS}, flush=True)
    summaries = {}
    for method in METHODS:
        rows = fold_rows[method]
        ba = np.array([row['balanced_accuracy'] for row in rows])
        summaries[method] = {'mean_subject_balanced_accuracy': float(ba.mean()), 'between_subject_sd': float(ba.std(ddof=1)),
                             'mean_subject_macro_f1': float(np.mean([row['macro_f1'] for row in rows])),
                             'subject_bootstrap_95_ci': bootstrap_ci(ba, diagnostic['seed']), 'per_subject': rows,
                             'portable_max_abs_error': max(row['portable_max_abs_error'] for row in rows)}
    comparisons = {m: paired_comparison(fold_rows[m], fold_rows['CSP_LDA'], diagnostic['seed']) for m in METHODS[1:]}
    for method in comparisons:
        comparisons[method]['continuation_gate_passed'] = passes_gate(summaries[method], comparisons[method], diagnostic['continuation_gate'])
    passing = [m for m in METHODS[1:] if comparisons[m]['continuation_gate_passed']]
    selected = max(passing, key=lambda m: summaries[m]['mean_subject_balanced_accuracy']) if passing else None
    scored_trials = int((order >= PREFIX_TRIALS).sum())
    if any(len(predictions[m]) != scored_trials for m in METHODS):
        raise ValueError('The four methods must share an identical scoring denominator')
    report = {'scope': 'Exploratory original-training-person LOSO; not an independent test or Cyton accuracy',
              'protocol': diagnostic, 'methods': summaries, 'paired_against_CSP_LDA': comparisons,
              'selected_for_later_independent_evaluation': selected, 'diagnostic_continuation_gate_passed': bool(passing),
              'participant_count': len(allowed), 'all_original_trials_retained': len(labels),
              'unscored_target_prefix_trials': len(allowed) * PREFIX_TRIALS, 'common_scored_trials': scored_trials,
              'author_flagged_trials_retained': sum(r['voltage_bad'] or r['emg_bad'] for r in manifest),
              'trials_discarded': 0, 'former_development_eeg_read': False, 'confirmation_eeg_read': False,
              'promotion_gate_passed': False, 'control_enabled': False,
              'pc_extraction_seconds': extraction_seconds, 'pc_fit_and_predict_seconds': fit_seconds,
              'pc_total_seconds': time.monotonic() - started}
    if selected:
        with threadpool_limits(limits=1):
            values = aligned if selected.startswith('EA_') else covs
            fitted = fit(values, ratios, labels, selected)
        save_fitted(args.output / 'training_only_candidate.npz', fitted,
                    {'method': selected, 'channels': list(FIXED), 'source_subjects': allowed,
                     'protocol_sha256': hashes(diagnostic_path)['sha256'], 'status': 'training_diagnostic_only',
                     'target_reference': 'own first60 unlabeled cued trials, then frozen' if selected.startswith('EA_') else None,
                     'sample_rate_hz': 250, 'window_samples': 500, 'epoch_after_cue_s': [.5, 2.5],
                     'pre_cue_baseline_s': [-1, 0], 'promotion_gate_passed': False, 'control_enabled': False})
    provenance['completed_at_local'] = datetime.now().isoformat()
    save(args.output / 'provenance.json', provenance)
    save(args.output / 'diagnostic.json', report)
    save(args.output / 'predictions.json', predictions)
    print(json.dumps({'means': {m: summaries[m]['mean_subject_balanced_accuracy'] for m in METHODS},
                      'passing': passing, 'selected': selected, 'common_scored_trials': scored_trials,
                      'promotion_gate_passed': False}, indent=2), flush=True)


if __name__ == '__main__':
    main()

"""Recompute saved predictions and paired gates without refitting or opening raw EEG."""
import argparse
import json
from pathlib import Path

import numpy as np

from cho2017_data import hashes
from cho2017_training_diagnostic import validate_protocol, paired_comparison, passes_gate
from mi_physionet_evaluate import bootstrap_ci

HERE = Path(__file__).resolve().parent
RELEASE = Path('D:/ican/handoff/GuardianLoop_FROZEN_20261001.zip')
RELEASE_SHA256 = '6ab91f2dceceeb96f199190f888035213eabf1195bc75146a1a766d9684c6530'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=HERE / 'output/cho2017_training_diagnostic_20261001')
    args = parser.parse_args()
    output = args.run / 'audit.json'
    if output.exists():
        raise RuntimeError('Existing audit preserved; use a fresh reproduction directory')
    report = json.loads((args.run / 'diagnostic.json').read_text(encoding='utf-8'))
    provenance = json.loads((args.run / 'provenance.json').read_text(encoding='utf-8'))
    protocol = report['protocol']
    original = json.loads((args.run / 'code_snapshot/cho2017_protocol.json').read_text(encoding='utf-8'))
    allowed = validate_protocol(original, protocol)
    if provenance['subjects_actually_read'] != allowed or provenance['old_mixed_feature_cache_loaded']:
        raise ValueError('Training-only extraction provenance disagrees')
    for path, digest in provenance['source_code_sha256'].items():
        if hashes(args.run / 'code_snapshot' / Path(path).name)['sha256'] != digest:
            raise ValueError('Saved code snapshot hash mismatch: ' + path)
    manifest = json.loads((args.run / 'trial_manifest.json').read_text(encoding='utf-8'))
    predictions = json.loads((args.run / 'predictions.json').read_text(encoding='utf-8'))
    with np.load(args.run / 'training_statistics.npz', allow_pickle=False) as stored:
        covs, subjects, order = stored['covariances'], stored['subjects'], stored['order']
        labels, baseline, task = stored['labels'], stored['baseline_variance'], stored['task_variance']
        ratios = np.log(np.maximum(task[:, :2], 1e-12) / np.maximum(baseline[:, :2], 1e-12)).reshape(len(task), 16)
        np.testing.assert_array_equal(ratios, stored['log_power_ratio'])
    if set(subjects) != set(allowed) or len(manifest) != len(labels):
        raise ValueError('Feature cache contains a forbidden person or wrong trial count')
    np.testing.assert_array_equal(labels, [r['label'] for r in manifest])
    np.testing.assert_array_equal(subjects, [r['subject'] for r in manifest])
    np.testing.assert_array_equal(order, [r['original_order'] for r in manifest])
    np.testing.assert_allclose(np.trace(covs, axis1=2, axis2=3), 1, atol=1e-10)
    aligned = covs.copy()
    with np.load(args.run / 'prefix_only_references.npz', allow_pickle=False) as reference_file:
        np.testing.assert_array_equal(reference_file['subjects'], allowed)
        for slot, person in enumerate(allowed):
            mask = subjects == person
            np.testing.assert_array_equal(order[mask], np.arange(mask.sum()))
            prefix = mask & (order < 60)
            if prefix.sum() != 60:
                raise ValueError('Wrong calibration prefix size')
            reference = .9 * covs[prefix, 2].mean(axis=0) + .1 * np.eye(8) / 8
            eigenvalues, vectors = np.linalg.eigh(reference)
            whitening = vectors @ np.diag(1 / np.sqrt(eigenvalues)) @ vectors.T
            np.testing.assert_allclose(reference, reference_file['regularized_reference'][slot], atol=1e-12)
            np.testing.assert_allclose(whitening, reference_file['whitening'][slot], atol=1e-12)
            values = whitening @ covs[mask, 2] @ whitening.T
            values = (values + values.transpose(0, 2, 1)) / 2
            aligned[mask, 2] = values / np.trace(values, axis1=1, axis2=2)[:, None, None]
    recomputed = {}
    score_errors = []
    expected_keys = [(r['subject'], r['original_order']) for r in manifest if r['original_order'] >= 60]
    for method in protocol['methods']:
        rows = predictions[method]
        if [(r['subject'], r['original_order']) for r in rows] != expected_keys:
            raise ValueError('Scoring denominator or order differs by method')
        person_metrics = []
        for person in allowed:
            mask = (subjects == person) & (order >= 60)
            records = [r for r in rows if r['subject'] == person]
            selected = aligned[mask] if method.startswith('EA_') else covs[mask]
            with np.load(args.run / f'fold_parameters/s{person:02d}_{method}.npz', allow_pickle=False) as parameters:
                metadata = json.loads(parameters['metadata'].item())
                if metadata['source_subjects'] != sorted(set(allowed) - {person}) or metadata['target_labels_used_for_fit']:
                    raise ValueError('Saved fold fitted on a held-out person')
                if method == 'ERD_LDA':
                    features = ratios[mask]
                else:
                    filters = parameters['filters'][0]
                    power = np.array([[f @ c @ f for f in filters] for c in selected[:, 2]])
                    features = np.log(np.maximum(power, 1e-12))
                    if method == 'EA_CSP_ERD_LDA':
                        features = np.concatenate([features, ratios[mask]], axis=1)
                scores = ((features - parameters['mean']) / parameters['scale']) @ parameters['coef'] + parameters['intercept']
            np.testing.assert_allclose(scores, [r['score'] for r in records], atol=1e-10, rtol=1e-10)
            predicted = (scores > 0).astype(int)
            np.testing.assert_array_equal(predicted, [r['prediction'] for r in records])
            np.testing.assert_array_equal(labels[mask], [r['label'] for r in records])
            score_errors.append(float(np.max(np.abs(scores - [r['score'] for r in records]))))
            confusion = np.zeros((2, 2), dtype=int)
            np.add.at(confusion, (labels[mask], predicted), 1)
            if np.any(confusion.sum(axis=1) == 0):
                raise ValueError('Both classes required for participant BA')
            ba = float(np.mean(np.diag(confusion) / confusion.sum(axis=1)))
            f1 = float(np.mean(2 * np.diag(confusion) / (confusion.sum(axis=1) + confusion.sum(axis=0))))
            person_metrics.append({'subject': person, 'balanced_accuracy': ba, 'macro_f1': f1,
                                   'trials': int(mask.sum()), 'confusion_matrix': confusion.tolist()})
        actual = report['methods'][method]
        np.testing.assert_allclose(np.mean([r['balanced_accuracy'] for r in person_metrics]), actual['mean_subject_balanced_accuracy'], atol=1e-12)
        np.testing.assert_allclose(np.mean([r['macro_f1'] for r in person_metrics]), actual['mean_subject_macro_f1'], atol=1e-12)
        np.testing.assert_allclose(bootstrap_ci([r['balanced_accuracy'] for r in person_metrics], protocol['seed']), actual['subject_bootstrap_95_ci'], atol=1e-12)
        for row, recorded in zip(person_metrics, actual['per_subject']):
            np.testing.assert_allclose(row['balanced_accuracy'], recorded['balanced_accuracy'], atol=1e-12)
            if recorded['source_subjects'] != sorted(set(allowed) - {row['subject']}) or recorded['source_trials'] != int((subjects != row['subject']).sum()):
                raise ValueError('Reported fold source population incorrect')
        recomputed[method] = person_metrics
    passing = []
    for method in protocol['methods'][1:]:
        comparison = paired_comparison(recomputed[method], recomputed['CSP_LDA'], protocol['seed'])
        actual = report['paired_against_CSP_LDA'][method]
        for field in ('mean_ba_gain', 'paired_bootstrap_95_ci', 'three_comparison_adjusted_98_3333_ci'):
            np.testing.assert_allclose(comparison[field], actual[field], atol=1e-12)
        passed = passes_gate(report['methods'][method], comparison, protocol['continuation_gate'])
        if passed != actual['continuation_gate_passed']:
            raise ValueError('Continuation gate incorrect')
        if passed:
            passing.append(method)
    selected = max(passing, key=lambda m: report['methods'][m]['mean_subject_balanced_accuracy']) if passing else None
    if selected != report['selected_for_later_independent_evaluation'] or bool(passing) != report['diagnostic_continuation_gate_passed']:
        raise ValueError('Candidate selection incorrect')
    if (args.run / 'training_only_candidate.npz').exists() != bool(selected):
        raise ValueError('Candidate artifact must exist only if training continuation gate passes')
    if report['promotion_gate_passed'] or report['control_enabled'] or report['former_development_eeg_read'] or report['confirmation_eeg_read']:
        raise ValueError('Unexpected promotion, control or forbidden participant read')
    release_hash = hashes(RELEASE)['sha256']
    if release_hash != RELEASE_SHA256:
        raise ValueError('Frozen recovery archive changed')
    audit = {'passed': True, 'audit_code_sha256': hashes(Path(__file__))['sha256'],
             'source_code_snapshot_hashes_verified': True, 'participants': allowed,
             'scored_trials_per_method': len(expected_keys), 'raw_eeg_opened_by_auditor': False,
             'stored_predictions_recomputed': True, 'prefix_reference_recomputed_without_labels_or_future': True,
             'maximum_independent_score_error': max(score_errors), 'paired_gates_recomputed': True,
             'selected_candidate': selected, 'per_subject_confusions': recomputed,
             'frozen_release_sha256': release_hash, 'board_contacted': False,
             'artifact_sha256': {name: hashes(args.run / name)['sha256'] for name in
                 ('diagnostic.json', 'predictions.json', 'training_statistics.npz', 'trial_manifest.json',
                  'source_sha256.json', 'provenance.json', 'prefix_only_references.npz')}}
    output.write_text(json.dumps(audit, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: audit[k] for k in ('passed', 'scored_trials_per_method', 'maximum_independent_score_error',
                                           'selected_candidate', 'frozen_release_sha256')}, indent=2), flush=True)


if __name__ == '__main__':
    main()

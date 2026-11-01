"""Independent integer-count audit; never fit a model or change confirmation."""
from datetime import datetime
from pathlib import Path
import json

import numpy as np
from cho2017_data import hashes

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_confirmation_20261001'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def check_counts(labels, predictions):
    if labels.shape != predictions.shape or set(labels) != {0, 1}:
        raise ValueError('Complete two-class labels required')
    if not set(predictions).issubset({0, 1}):
        raise ValueError('Unknown class')
    matrix = np.zeros((2, 2), dtype=np.int64)
    np.add.at(matrix, (labels, predictions), 1)
    ba = float(np.mean(matrix.diagonal() / matrix.sum(axis=1)))
    macro_f1 = float(np.mean(2 * matrix.diagonal() / (matrix.sum(axis=0) + matrix.sum(axis=1))))
    return ba, macro_f1, matrix.tolist()


def interval(values, settings):
    values = np.array(values, dtype=np.float64)
    rng = np.random.default_rng(settings['seed'])
    samples = values[rng.integers(0, len(values), size=(settings['draws'], len(values)))].mean(axis=1)
    return np.quantile(samples, [.025, .975]).tolist()


def audit():
    protocol, result = read(RUN / 'protocol.json'), read(RUN / 'results.json')
    manifest, extraction = read(RUN / 'trial_manifest.json'), read(RUN / 'extraction.json')
    roles = [set(protocol[key]) for key in ('fit_people', 'validation_people',
                                          'confirmation_people', 'former_development_excluded')]
    if any(roles[i] & roles[j] for i in range(4) for j in range(i + 1, 4)):
        raise ValueError('Overlapping people')
    if set.union(*roles) != set(range(1, 53)):
        raise ValueError('Unexpected participant coverage')
    with np.load(RUN / 'confirmation_cache.npz', allow_pickle=False) as cache:
        labels, subjects, order = (cache[key] for key in ('labels', 'subjects', 'order'))
    if len(labels) != len(manifest) or len(labels) != extraction['trials']:
        raise ValueError('Trial manifest denominator mismatch')
    identities = [(row['subject'], row['original_order']) for row in manifest]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate original trial')
    for i, row in enumerate(manifest):
        if (row['subject'], row['original_order'], row['label']) != (subjects[i], order[i], labels[i]):
            raise ValueError('Trial manifest identity or label changed')
    for person in protocol['confirmation_people']:
        mask = subjects == person
        if not np.array_equal(order[mask], np.arange(mask.sum())):
            raise ValueError('Missing or reordered original trials')
        if np.bincount(labels[mask]).tolist() not in ([100, 100], [120, 120]):
            raise ValueError('Incomplete original left/right trials')
        keys = [row['original_sequence_key'] for row in manifest if row['subject'] == person]
        if len(set(keys)) != len(keys) or keys != sorted(keys):
            raise ValueError('Original chronological keys changed')
    scored = np.flatnonzero(order >= 60)
    rows_by_method, total = {}, 0
    for name in ('B1', 'seed42', 'seed43', 'seed44'):
        path = RUN / 'predictions' / f'{name}.npz'
        if hashes(path)['sha256'] != result['prediction_sha256'][path.name]:
            raise ValueError('Scored prediction file changed')
        with np.load(path, allow_pickle=False) as values:
            np.testing.assert_array_equal(values['indices'], scored)
            np.testing.assert_array_equal(values['labels'], labels[scored])
            predictions = values['predictions']
            if not np.isfinite(values['scores']).all():
                raise ValueError('Nonfinite scores')
            if name != 'B1':
                np.testing.assert_array_equal(values['cpu_scores'].argmax(axis=1), predictions)
        rows = []
        for index, person in enumerate(protocol['confirmation_people']):
            mask = subjects[scored] == person
            ba, f1, matrix = check_counts(labels[scored][mask], predictions[mask])
            saved = result['methods'][name]['per_subject'][index]
            if saved['subject'] != person or matrix != saved['confusion_matrix']:
                raise ValueError('Stored confusion matrix mismatch')
            np.testing.assert_allclose([ba, f1], [saved['balanced_accuracy'], saved['macro_f1']],
                                       rtol=0, atol=1e-14)
            if int(mask.sum()) != saved['trials']:
                raise ValueError('Stored scoring denominator mismatch')
            rows.append((ba, f1))
        rows_by_method[name] = np.array(rows)
        np.testing.assert_allclose(interval(np.array(rows)[:, 0], protocol['bootstrap']),
                                   result['methods'][name]['subject_bootstrap_95_ci'], rtol=0, atol=1e-14)
        total += len(scored)
    average = np.mean([rows_by_method[f'seed{seed}'] for seed in (42, 43, 44)], axis=0)
    primary = result['methods']['EEGNet_three_seed_mean']
    np.testing.assert_allclose(average[:, 0], [row['balanced_accuracy'] for row in primary['per_subject']],
                               rtol=0, atol=1e-14)
    np.testing.assert_allclose(average.mean(axis=0),
        [primary['mean_subject_balanced_accuracy'], primary['mean_subject_macro_f1']], rtol=0, atol=1e-14)
    differences = average[:, 0] - rows_by_method['B1'][:, 0]
    comparison = result['paired_against_B1']
    np.testing.assert_allclose([differences.mean(), *interval(differences, protocol['bootstrap'])],
        [comparison['mean_ba_gain'], *comparison['paired_bootstrap_95_ci']], rtol=0, atol=1e-14)
    g, a = protocol['confirmation_gate'], protocol['artifact_gate']
    checks = {
        'primary_mean': float(average[:, 0].mean()) >= g['mean_ba_at_least'],
        'primary_absolute_interval': interval(average[:, 0], protocol['bootstrap'])[0] > g['absolute_ci_lower_greater_than'],
        'paired_gain': float(differences.mean()) >= g['paired_gain_at_least'],
        'paired_interval': interval(differences, protocol['bootstrap'])[0] > g['paired_ci_lower_greater_than'],
        'seed42_mean': float(rows_by_method['seed42'][:, 0].mean()) >= a['mean_ba_at_least'],
        'seed42_absolute_interval': interval(rows_by_method['seed42'][:, 0], protocol['bootstrap'])[0] > a['absolute_ci_lower_greater_than']}
    checks.update(confirmation_gate_passed=all(checks[key] for key in list(checks)[:4]),
                  artifact_gate_passed=checks['seed42_mean'] and checks['seed42_absolute_interval'],
                  arm_eligible=all(checks.values()))
    if checks != result['decision']:
        raise ValueError('Independent gate recomputation differs')
    output = {'completed_at_local': datetime.now().isoformat(), 'auditor_sha256': hashes(Path(__file__))['sha256'],
        'results_sha256': hashes(RUN / 'results.json')['sha256'], 'trials_checked': len(labels),
        'predicted_labels_checked': total, 'all_person_trial_identities_unique': True,
        'all_original_trials_retained': True, 'metrics_from_integer_confusions_match': True,
        'bootstrap_and_all_gates_match': True, 'decision': checks,
        'confirmation_retrained': False, 'board_accessed': False, 'control_enabled': False}
    path = RUN / 'integer_count_audit.json'
    if path.exists():
        raise RuntimeError('Preserve existing independent audit')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(output, indent=2), flush=True)


if __name__ == '__main__':
    audit()

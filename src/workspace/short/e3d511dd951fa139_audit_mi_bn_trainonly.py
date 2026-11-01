"""Independent NumPy integer/statistical audit; no Torch or EEG forwards."""
from datetime import datetime
from pathlib import Path
import json
import numpy as np
from audit_mi_person_transfer_counts import read, digest, close

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_bn_trainonly_20261002'
BASES = {'CROSS_SOURCE_BN': 'CROSS_ORIGINAL', 'PERSON_BN': 'PERSON_ONLY', 'MATCHED80_BN': 'CROSS_MATCHED80'}


def main():
    target = RUN / 'integer_count_audit.json'
    if target.exists():
        raise RuntimeError('Existing independent audit preserved')
    p = read(RUN / 'protocol.json')
    result = read(RUN / 'results.json')
    cases = read(RUN / 'case_manifest.json')
    lock, freeze, access = [read(RUN / name) for name in ('lock.json', 'source_freeze.json', 'target_access.json')]
    assert len(cases) == 90 and freeze['calibrated_objects'] == 270
    assert not freeze['new_test_forwarded'] and not freeze['learned_weights_changed']
    assert datetime.fromisoformat(lock['declared_at_local']) < datetime.fromisoformat(freeze['at_local']) < datetime.fromisoformat(access['at_local'])
    for path, expected in {**lock['source_sha256'], **lock['input_sha256'], **freeze['files']}.items():
        assert digest(Path(path)) == expected, path
    assert digest(RUN / 'case_manifest.json') == lock['case_manifest_sha256']
    prior = HERE / p['prior_run']
    assert cases == read(prior / 'case_manifest.json')
    original = HERE / read(prior / 'protocol.json')['original_run']
    manifest = read(original / 'trial_manifest.json')
    with np.load(original / 'statistics.npz', allow_pickle=False) as stats:
        labels, people, order = [stats[k] for k in ('labels', 'subjects', 'order')]
    assert len(labels) == len(manifest) == 6080
    assert sorted(set(people)) == p['participants']
    assert sum(r['voltage_bad'] or r['emg_bad'] for r in manifest) == 515
    for case in cases:
        expected_test = np.flatnonzero((people == case['person']) & (order >= 120))
        np.testing.assert_array_equal(case['test'], expected_test)
        for method in BASES:
            metadata = read(RUN / 'models' / f's{case["person"]:02d}_{method}_seed{case["seed"]}.json')
            if method == 'CROSS_SOURCE_BN':
                fit = np.flatnonzero(np.isin(people, case['original_source_fold']['fit_people']))
                assert case['person'] not in people[fit]
                assert not set(people[fit]) & set(case['original_source_fold']['validation_people'])
            elif method == 'PERSON_BN':
                fit = np.flatnonzero((people == case['person']) & (order < 80))
                assert len(fit) == 80 and not set(fit) & set(case['personal_validation'])
            else:
                fit = np.array(case['matched_fit'])
                assert len(fit) == len(set(fit)) == 80
                assert not set(fit) & set(case['matched_validation'])
                assert set(people[fit]) == set(case['original_source_fold']['fit_people'])
            np.testing.assert_array_equal(metadata['fit_indices'], fit)
            assert not set(fit) & set(case['test'])
            assert metadata['learned_tensors_exact'] and metadata['dropout_disabled']
            assert not metadata['labels_used'] and not metadata['new_test_forward']
            assert all(k.endswith(('.running_mean', '.running_var', '.num_batches_tracked')) for k in metadata['only_BN_buffers_changed'])
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 30, (10000, 30))
    arrays, total = {}, 0
    for method in p['methods']:
        rows = result['methods'][method]['per_person']
        assert [r['person'] for r in rows] == p['participants']
        values, f1s = [], []
        for row in rows:
            bas, fs = [], []
            for case in [c for c in cases if c['person'] == row['person']]:
                path = RUN / 'fold_predictions' / f's{case["person"]:02d}_{method}_seed{case["seed"]}.npz'
                assert digest(path) == result['prediction_sha256'][str(path)]
                with np.load(path, allow_pickle=False) as saved:
                    ids, y, pred = saved['indices'], saved['labels'], saved['predictions']
                    np.testing.assert_array_equal(ids, case['test'])
                    np.testing.assert_array_equal(y, labels[ids])
                    np.testing.assert_array_equal(pred, saved['scores'].argmax(1))
                    if method not in BASES:
                        oldpath = prior / 'fold_predictions' / path.name
                        with np.load(oldpath, allow_pickle=False) as old:
                            for key in ('indices', 'labels', 'scores', 'predictions'):
                                np.testing.assert_array_equal(saved[key], old[key])
                    matrix = [[int(sum((y == i) & (pred == j))) for j in (0, 1)] for i in (0, 1)]
                    ba = sum(matrix[i][i] / sum(matrix[i]) for i in (0, 1)) / 2
                    f1 = sum(2 * matrix[i][i] / (sum(matrix[i]) + sum(matrix[j][i] for j in (0, 1))) for i in (0, 1)) / 2
                expected = next(r for r in row['per_seed'] if r['seed'] == case['seed'])
                assert matrix == expected['confusion']
                close([ba, f1], [expected['ba'], expected['macro_f1']])
                bas.append(ba); fs.append(f1); total += len(ids)
            close([np.mean(bas), np.mean(fs)], [row['ba'], row['macro_f1']])
            values.append(np.mean(bas)); f1s.append(np.mean(fs))
        values = np.array(values)
        summary = result['methods'][method]
        close([values.mean(), values.std(ddof=1), np.sort(values)[:8].mean(), np.mean(f1s)],
              [summary['mean_person_ba'], summary['between_person_sd'], summary['mean_lowest8_ba'], summary['mean_person_f1']])
        close(np.quantile(values[draws].mean(1), [.025, .975]), summary['person95ci'])
        arrays[method] = values
    for primary, pairs in ((True, p['primary_comparisons']), (False, p['secondary_comparisons'])):
        for pair in pairs:
            name = pair['candidate'] + '_minus_' + pair['reference']
            c = result['comparisons'][name]
            delta = arrays[pair['candidate']] - arrays[pair['reference']]
            tail = (1 - p['bootstrap']['primary_interval' if primary else 'secondary_interval']) / 2
            ci = np.quantile(delta[draws].mean(1), [tail, 1 - tail])
            close(c['mean_gain'], delta.mean()); close(c['paired_ci'], ci); close(c['per_person_delta'], delta)
            assert c['primary'] == primary and c['gain_threshold'] == pair.get('gain_at_least')
            assert c['development_gate'] == bool(primary and delta.mean() >= pair['gain_at_least'] and ci[0] > 0)
            assert c['people_improved'] == int(sum(delta > 1e-12)) and c['people_declined'] == int(sum(delta < -1e-12))
    unique = {i for c in cases for i in c['test']}
    assert len(unique) == result['scored_unique_trials'] == 2480
    assert result['scored_author_flags'] == 198 == sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique)
    assert total == 44640 and len(result['prediction_sha256']) == 540
    result_audit = {'passed': True, 'integer_predictions_checked': total, 'unchanged_baseline_arrays_exact': True,
        'all_train_only_indices_checked': True, 'all_confusions_metrics_intervals_gates_recomputed': True,
        'states_frozen_before_new_scoring': True, 'unique_trials': 2480, 'test_author_flags': 198,
        'model_fitted': False, 'raw_mat_read': False, 'board_accessed': False,
        'results_sha256': digest(RUN / 'results.json'), 'script_sha256': digest(Path(__file__)), 'at_local': datetime.now().isoformat()}
    target.write_text(json.dumps(result_audit, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result_audit, indent=2))


if __name__ == '__main__':
    main()

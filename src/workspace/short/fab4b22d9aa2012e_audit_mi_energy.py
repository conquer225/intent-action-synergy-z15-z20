"""Independent integer metrics, source statistics, scope and baseline audit."""
from datetime import datetime
from pathlib import Path
import json
import numpy as np
from audit_mi_person_transfer_counts import read, digest, close

HERE = Path(__file__).resolve().parent
RUN = HERE/'output/mi_energy_source_diagnostic_20261002'


def counts(y, prediction):
    matrix = np.array([[int(np.sum((y == a)&(prediction == b))) for b in (0, 1)] for a in (0, 1)])
    ba = float(np.mean(np.diag(matrix)/matrix.sum(1)))
    f1 = float(np.mean(2*np.diag(matrix)/(matrix.sum(0)+matrix.sum(1))))
    return ba, f1, matrix.tolist()


def main():
    destination = RUN/'integer_count_audit.json'
    if destination.exists():
        raise RuntimeError('Completed audit preserved')
    p, result, lock, freeze, access = [read(RUN/name) for name in
        ('protocol.json', 'results.json', 'lock.json', 'source_freeze.json', 'validation_access.json')]
    assert freeze['new_fits'] == 60 and freeze['reused_models'] == 30 and freeze['total_states'] == 90
    assert len(freeze['files']) == 180
    assert lock['at_local'] < freeze['at_local'] < access['at_local']
    assert not freeze['source_validation_scored'] and not freeze['outer_target_scored']
    assert access['source_validation_only'] and not access['outer_target_scored']
    for path, expected in {**lock['source_sha256'], **lock['input_sha256'], **freeze['files'], **result['prediction_sha256']}.items():
        assert digest(Path(path)) == expected, path
    assert digest(RUN/'source_fold_manifest.json') == lock['source_fold_manifest_sha256']
    feature_audit = read(RUN/'feature_audit.json')
    assert digest(RUN/'features.npz') == feature_audit['features_sha256']
    assert feature_audit['all6080_scale_identity_probes'] and feature_audit['stateless_label_free']
    assert feature_audit['normalized_byte_identical'] and not feature_audit['outer_target_scored']
    original = HERE/p['original_run']
    manifest = read(original/'trial_manifest.json')
    old_folds = read(original/'fold_manifest.json')
    folds = read(RUN/'source_fold_manifest.json')
    with np.load(original/'statistics.npz', allow_pickle=False) as saved:
        labels, people = saved['labels'].copy(), saved['subjects'].copy()
    assert len(labels) == len(manifest) == 6080
    np.testing.assert_array_equal(labels, [row['label'] for row in manifest])
    np.testing.assert_array_equal(people, [row['subject'] for row in manifest])
    assert sum(row['voltage_bad'] or row['emg_bad'] for row in manifest) == 515
    with np.load(RUN/'features.npz', allow_pickle=False) as saved:
        features = {method: saved[method].copy() for method in p['methods']}
    np.testing.assert_array_equal(features['NORMALIZED'], np.load(HERE/p['baseline_feature_cache'], allow_pickle=False))
    np.testing.assert_array_equal(features['NORMALIZED_ENERGY'][:, :36], features['NORMALIZED'])
    waves = np.load(original/'waveforms.npy', allow_pickle=False).astype(np.float64)
    energy = np.log(np.var(waves, axis=2, ddof=1).sum(1))
    close(features['NORMALIZED_ENERGY'][:, -1], energy)
    expected_absolute = features['NORMALIZED'].copy()
    diagonal = np.array([i for i, (a, b) in enumerate(zip(*np.triu_indices(8))) if a == b])
    expected_absolute[:, diagonal] += energy[:, None]
    np.testing.assert_array_equal(features['ABSOLUTE'], expected_absolute)
    del waves
    validation_people = sorted({person for fold in folds for person in fold['validation_people']})
    assert len(validation_people) == 28 and validation_people == result['validation_people']
    assert set(p['participants'])-set(validation_people) == {14, 28}
    appearances = {person: sum(person in f['validation_people'] for f in folds) for person in validation_people}
    assert sum(appearances.values()) == 90 and min(appearances.values()) == 1 and max(appearances.values()) == 7
    values, total, unique = {}, 0, set()
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 28, (10000, 28))
    for method in p['methods']:
        history = {person: [] for person in validation_people}
        training_means = []
        for fold, old_fold in zip(folds, old_folds):
            assert all(fold[key] == old_fold[key] for key in old_fold)
            fit = np.flatnonzero(np.isin(people, fold['fit_people']))
            val = np.flatnonzero(np.isin(people, fold['validation_people']))
            np.testing.assert_array_equal(fit, fold['fit_indices'])
            np.testing.assert_array_equal(val, fold['validation_indices'])
            assert len(set(people[fit])) == 26 and len(set(people[val])) == 3 and not (set(fit)&set(val))
            assert fold['target'] not in people[fit] and fold['target'] not in people[val]
            unique.update(val.tolist())
            model_path = RUN/'models'/f'outer{fold["target"]:02d}_{method}.npz'
            meta = read(model_path.with_suffix('.json'))
            assert meta['C'] == .1 and meta['dimensions'] == p['dimensions'][method]
            assert not meta['source_validation_used_for_selection'] and not meta['outer_target_scored']
            with np.load(model_path, allow_pickle=False) as state:
                np.testing.assert_array_equal(state['fit_indices'], fit)
                close(state['mean'], features[method][fit].mean(0))
                scale = features[method][fit].std(0)
                scale[scale == 0] = 1
                close(state['scale'], scale)
                assert float(state['factor']) == 1.
                margins = ((features[method]-state['mean'])/state['scale'])@state['coef']+state['intercept']
                training_ba = np.mean([counts(labels[fit][people[fit] == person], (margins[fit][people[fit] == person]>0).astype(int))[0] for person in fold['fit_people']])
                close(training_ba, meta['source_fit_mean_person_ba'])
                training_means.append(float(training_ba))
            pred_path = RUN/'validation_predictions'/f'outer{fold["target"]:02d}_{method}.npz'
            if method == 'NORMALIZED':
                baseline_model = HERE/p['baseline_run']/'models'/f'outer{fold["target"]:02d}_WHOLE.npz'
                assert digest(model_path) == digest(baseline_model)
            with np.load(pred_path, allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['indices'], val)
                np.testing.assert_array_equal(saved['people'], people[val])
                np.testing.assert_array_equal(saved['labels'], labels[val])
                close(saved['scores'], margins[val])
                np.testing.assert_array_equal(saved['predictions'], (margins[val]>0).astype(int))
                if method == 'NORMALIZED':
                    old_path = HERE/p['baseline_run']/'validation_predictions'/f'outer{fold["target"]:02d}_WHOLE.npz'
                    with np.load(old_path, allow_pickle=False) as old:
                        for key in saved.files:
                            np.testing.assert_array_equal(saved[key], old[key])
                for person in fold['validation_people']:
                    keep = people[val] == person
                    ba, f1, matrix = counts(labels[val][keep], saved['predictions'][keep])
                    history[person].append({'outer_fold': fold['target'], 'trials': int(keep.sum()),
                        'ba': ba, 'macro_f1': f1, 'confusion': matrix})
                total += len(val)
        rows = result['methods'][method]['per_person']
        assert [row['person'] for row in rows] == validation_people
        for row in rows:
            actual = history[row['person']]
            assert len(actual) == appearances[row['person']]
            for saved, rebuilt in zip(row['appearances'], actual):
                assert saved['outer_fold'] == rebuilt['outer_fold'] and saved['trials'] == rebuilt['trials']
                assert saved['confusion'] == rebuilt['confusion']
                close([saved['ba'], saved['macro_f1']], [rebuilt['ba'], rebuilt['macro_f1']])
            close(row['ba'], np.mean([a['ba'] for a in actual]))
            close(row['macro_f1'], np.mean([a['macro_f1'] for a in actual]))
        v = np.array([row['ba'] for row in rows])
        summary = result['methods'][method]
        values[method] = v
        close([v.mean(), v.std(ddof=1), np.sort(v)[:7].mean(), np.mean([row['macro_f1'] for row in rows]), np.mean(training_means)],
              [summary['mean_person_ba'], summary['between_person_sd'], summary['mean_lowest7_ba'], summary['mean_person_f1'], summary['descriptive_source_fit_mean_ba']])
        close(np.quantile(v[draws].mean(1), [.025, .975]), summary['descriptive_person95ci'])
    for i, (candidate, reference) in enumerate([[p['primary_candidate'], p['primary_reference']]]+p['secondary_comparisons']):
        actual = result['comparisons'][candidate+'_minus_'+reference]
        delta = values[candidate]-values[reference]
        interval = np.quantile(delta[draws].mean(1), [.025, .975])
        weak = np.sort(values[candidate])[:7].mean()-np.sort(values[reference])[:7].mean()
        close(actual['mean_gain'], delta.mean())
        close(actual['per_person_delta'], delta)
        close(actual['descriptive_paired_ci'], interval)
        close(actual['lowest7_mean_difference'], weak)
        assert actual['primary'] == (i == 0)
        assert actual['direction_gate'] == bool(i == 0 and delta.mean() >= .02 and interval[0] > 0 and weak >= -.01)
        assert actual['people_improved'] == int((delta>1e-12).sum()) and actual['people_declined'] == int((delta< -1e-12).sum())
    assert total == result['total_predictions'] == 54840 and len(result['prediction_sha256']) == 90
    assert len(unique) == result['unique_validation_trials'] == 5680 and result['person_appearances'] == 90
    assert sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique) == result['unique_validation_author_flags'] == 510
    for field in ('outer_target_scored', 'board_accessed', 'arm_exported', 'control_enabled'):
        assert result[field] is False
    report = {'passed': True, 'integer_predictions_checked': total, 'new_fits_checked': 60,
        'states_checked': 90, 'unique_validation_people': 28, 'unique_validation_trials': 5680,
        'author_flags_retained': 510, 'source_statistics_and_indices_checked': True,
        'source_fit_means_checked': True, 'baseline_states_byte_identical': True,
        'baseline_prediction_arrays_identical': True, 'person_weighting_and_primary_gate_checked': True,
        'outer_target_scored': False, 'results_sha256': digest(RUN/'results.json'),
        'script_sha256': digest(Path(__file__)), 'at_local': datetime.now().isoformat()}
    destination.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

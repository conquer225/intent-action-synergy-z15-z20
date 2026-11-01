"""Independent NumPy arrays, maps, counts, averaging and frozen-file audit."""
from datetime import datetime
from pathlib import Path
import json
import numpy as np
from audit_mi_person_transfer_counts import read, digest, close

HERE = Path(__file__).resolve().parent
RUN = HERE/'output/mi_readout_source_diagnostic_20261002'


def metric(y, prediction):
    confusion = np.array([[np.sum((y == a)&(prediction == b)) for b in (0, 1)] for a in (0, 1)], dtype=int)
    ba = float(np.mean(np.diag(confusion)/confusion.sum(1)))
    f1 = float(np.mean(2*np.diag(confusion)/(confusion.sum(0)+confusion.sum(1))))
    return ba, f1, confusion.tolist()


def main():
    target = RUN/'integer_count_audit.json'
    if target.exists():
        raise RuntimeError('Completed audit preserved')
    p, r, lock, freeze, access = [read(RUN/name) for name in
        ('protocol.json', 'results.json', 'lock.json', 'source_freeze.json', 'validation_access.json')]
    assert freeze['new_fits'] == 180 and freeze['reused_models'] == 30 and freeze['total_states'] == 210
    assert len(freeze['files']) == 420 and not freeze['source_validation_scored'] and not freeze['outer_target_scored']
    assert lock['at_local'] < read(RUN/'map_freeze.json')['at_local'] < freeze['at_local'] < access['at_local']
    assert access['source_validation_only'] and not access['outer_target_scored']
    maps = read(RUN/'map_freeze.json')['files']
    for source, expected in {**lock['source_sha256'], **lock['input_sha256'], **freeze['files'], **maps, **r['prediction_sha256']}.items():
        assert digest(Path(source)) == expected, source
    assert digest(RUN/'source_fold_manifest.json') == lock['source_fold_manifest_sha256']
    original = HERE/p['original_run']
    old_folds = read(original/'fold_manifest.json')
    folds = read(RUN/'source_fold_manifest.json')
    manifest = read(original/'trial_manifest.json')
    with np.load(original/'statistics.npz', allow_pickle=False) as stored:
        people, labels = stored['subjects'].copy(), stored['labels'].copy()
    features = np.load(HERE/p['baseline_feature_cache'], allow_pickle=False)
    np.testing.assert_array_equal(people, [a['subject'] for a in manifest])
    np.testing.assert_array_equal(labels, [a['label'] for a in manifest])
    assert len(manifest) == 6080 and sum(a['voltage_bad'] or a['emg_bad'] for a in manifest) == 515
    weights, offsets = {}, {}
    for seed in p['seeds']:
        rng = np.random.RandomState(seed)
        weights[seed] = rng.normal(size=(36, 128))/6
        offsets[seed] = rng.uniform(0, 2*np.pi, 128)
        with np.load(RUN/'maps'/f'seed{seed}.npz', allow_pickle=False) as saved:
            np.testing.assert_allclose(weights[seed], saved['weights'], rtol=1e-15, atol=1e-15)
            np.testing.assert_array_equal(offsets[seed], saved['offset'])
    validation_people = sorted({person for fold in folds for person in fold['validation_people']})
    assert validation_people == r['validation_people'] and len(validation_people) == 28
    assert set(p['participants'])-set(validation_people) == {14, 28}
    appearances = {person: sum(person in f['validation_people'] for f in folds) for person in validation_people}
    assert min(appearances.values()) == 1 and max(appearances.values()) == 7 and sum(appearances.values()) == 90
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 28, (10000, 28))
    total = 0
    unique = set()
    values = {}
    old_prediction_hashes = read(HERE/p['baseline_run']/'results.json')['prediction_sha256']
    for method in p['methods']:
        seeds = [0] if method == 'LINEAR' else p['seeds']
        cases = {person: [] for person in validation_people}
        train_means = {seed: [] for seed in seeds}
        for fold, old in zip(folds, old_folds):
            assert all(fold[key] == old[key] for key in old)
            fit = np.flatnonzero(np.isin(people, fold['fit_people']))
            val = np.flatnonzero(np.isin(people, fold['validation_people']))
            np.testing.assert_array_equal(fit, fold['fit_indices'])
            np.testing.assert_array_equal(val, fold['validation_indices'])
            assert len(set(people[fit])) == 26 and len(set(people[val])) == 3
            assert not set(fit)&set(val) and fold['target'] not in people[fit] and fold['target'] not in people[val]
            unique.update(val.tolist())
            for seed in seeds:
                model = RUN/'models'/f'outer{fold["target"]:02d}_{method}_s{seed}.npz'
                meta = read(model.with_suffix('.json'))
                assert meta['method'] == method and meta['seed'] == seed and meta['C'] == .1
                assert not meta['source_validation_used_for_selection'] and not meta['outer_target_scored']
                assert meta['dimensions'] == p['dimensions'][method] and meta['new_fit'] == (method != 'LINEAR')
                with np.load(model, allow_pickle=False) as state:
                    np.testing.assert_array_equal(state['fit_indices'], fit)
                    expected_scale = features[fit].std(0)
                    expected_scale[expected_scale == 0] = 1
                    np.testing.assert_allclose(state['mean'], features[fit].mean(0), rtol=1e-10, atol=1e-10)
                    np.testing.assert_allclose(state['scale'], expected_scale, rtol=1e-10, atol=1e-10)
                    zfit = (features[fit]-state['mean'])/state['scale']
                    zval = (features[val]-state['mean'])/state['scale']
                    if method == 'LINEAR':
                        assert state['factor'] == 1 and digest(model) == meta['reused_source_sha256'] == digest(Path(meta['reused_source']))
                        fvalues, vvalues = zfit, zval
                    else:
                        fproj = np.einsum('ij,jk->ik', zfit, weights[seed])
                        vproj = np.einsum('ij,jk->ik', zval, weights[seed])
                        if method == 'LINEAR_PROJECTED':
                            fextra, vextra = fproj/np.sqrt(128), vproj/np.sqrt(128)
                        else:
                            fextra = np.exp(1j*(fproj+offsets[seed])).real*np.sqrt(2/128)
                            vextra = np.exp(1j*(vproj+offsets[seed])).real*np.sqrt(2/128)
                        mean = fextra.mean(0)
                        scale = np.sqrt(18/np.mean(np.sum((fextra-mean)**2, axis=1)))
                        np.testing.assert_allclose(state['aux_mean'], mean, rtol=5e-9, atol=5e-9)
                        np.testing.assert_allclose(state['aux_scale'], scale, rtol=5e-9, atol=5e-9)
                        fvalues = np.column_stack((zfit/np.sqrt(2), (fextra-mean)*scale))
                        vvalues = np.column_stack((zval/np.sqrt(2), (vextra-mean)*scale))
                        np.testing.assert_allclose(np.mean(np.sum(fvalues**2, axis=1)), 36, rtol=5e-9, atol=5e-9)
                    margins = vvalues@state['coef']+state['intercept']
                    fpred = (fvalues@state['coef']+state['intercept'] > 0).astype(int)
                    expected_train = []
                    for person in sorted(set(people[fit])):
                        keep = people[fit] == person
                        ba, f1, _ = metric(labels[fit][keep], fpred[keep])
                        expected_train.append({'person': int(person), 'ba': ba, 'macro_f1': f1})
                    assert meta['source_fit_metrics']['people'] == expected_train
                    close(meta['source_fit_metrics']['mean_person_ba'], np.mean([a['ba'] for a in expected_train]))
                    train_means[seed].append(meta['source_fit_metrics']['mean_person_ba'])
                prediction_path = RUN/'validation_predictions'/model.name
                with np.load(prediction_path, allow_pickle=False) as saved:
                    np.testing.assert_array_equal(saved['indices'], val)
                    np.testing.assert_array_equal(saved['labels'], labels[val])
                    np.testing.assert_array_equal(saved['people'], people[val])
                    np.testing.assert_allclose(saved['scores'], margins, rtol=5e-9, atol=5e-9)
                    np.testing.assert_array_equal(saved['predictions'], (margins > 0).astype(int))
                    if method == 'LINEAR':
                        old_path = HERE/p['baseline_run']/'validation_predictions'/f'outer{fold["target"]:02d}_WHOLE.npz'
                        assert digest(old_path) == old_prediction_hashes[str(old_path)]
                        with np.load(old_path, allow_pickle=False) as old_saved:
                            for key in ('indices', 'people', 'labels', 'scores', 'predictions'):
                                np.testing.assert_array_equal(saved[key], old_saved[key])
                    for person in fold['validation_people']:
                        keep = people[val] == person
                        ba, f1, cm = metric(labels[val][keep], saved['predictions'][keep])
                        cases[person].append({'outer_fold': fold['target'], 'seed': seed,
                            'trials': int(keep.sum()), 'ba': ba, 'macro_f1': f1, 'confusion': cm})
                total += len(val)
        rows = r['methods'][method]['per_person']
        assert [row['person'] for row in rows] == validation_people
        seed_means = []
        for row in rows:
            assert row['cases'] == cases[row['person']]
            expected = []
            for seed in seeds:
                subset = [case for case in cases[row['person']] if case['seed'] == seed]
                assert len(subset) == appearances[row['person']]
                expected.append({'seed': seed, 'ba': float(np.mean([a['ba'] for a in subset])),
                    'macro_f1': float(np.mean([a['macro_f1'] for a in subset])), 'appearances': len(subset)})
            assert row['per_seed'] == expected
            close(row['ba'], np.mean([a['ba'] for a in expected]))
            close(row['macro_f1'], np.mean([a['macro_f1'] for a in expected]))
        m = r['methods'][method]
        vals = np.array([a['ba'] for a in rows])
        values[method] = vals
        close([vals.mean(), vals.std(ddof=1), np.sort(vals)[:7].mean(), np.mean([a['macro_f1'] for a in rows])],
              [m['mean_person_ba'], m['between_person_sd'], m['mean_lowest7_ba'], m['mean_person_f1']])
        close(np.quantile(vals[draws].mean(1), [.025, .975]), m['descriptive_person95ci'])
        for index, seed in enumerate(seeds):
            average = float(np.mean([a['per_seed'][index]['ba'] for a in rows]))
            close(average, m['seed_mean_ba'][str(seed)])
            seed_means.append(average)
            close(train_means[seed], m['source_fit_seed_fold_ba'][str(seed)])
        close(np.std(seed_means, ddof=1) if len(seeds) > 1 else 0, m['seed_mean_sd'])
        close(np.mean(list(train_means.values())), m['descriptive_source_fit_mean_ba'])
    settings = p['co_primary']+[{'candidate': pair[0], 'reference': pair[1]} for pair in p['secondary']]
    decisions = []
    for index, setting in enumerate(settings):
        candidate, reference = setting['candidate'], setting['reference']
        comparison = r['comparisons'][candidate+'_minus_'+reference]
        delta = values[candidate]-values[reference]
        alpha = .0125 if index < 2 else .025
        ci = np.quantile(delta[draws].mean(1), [alpha, 1-alpha])
        weak = np.sort(values[candidate])[:7].mean()-np.sort(values[reference])[:7].mean()
        close(comparison['mean_gain'], delta.mean())
        close(comparison['per_person_delta'], delta)
        close(comparison['descriptive_paired_ci'], ci)
        close(comparison['lowest7_mean_difference'], weak)
        assert comparison['co_primary'] == (index < 2) and comparison['nominal_coverage'] == 1-2*alpha
        expected_gate = bool(delta.mean() >= setting['minimum_gain'] and ci[0] > 0 and weak >= -.01) if index < 2 else False
        assert comparison['direction_gate'] == expected_gate
        if index < 2:
            decisions.append(expected_gate)
        assert comparison['people_improved'] == int((delta > 1e-12).sum())
        assert comparison['people_declined'] == int((delta < -1e-12).sum())
    assert r['nominate_for_later_locked_comparison'] == all(decisions)
    assert total == r['total_predictions'] == 127960 and len(r['prediction_sha256']) == 210
    assert len(unique) == r['unique_validation_trials'] == 5680
    assert sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique) == r['unique_validation_author_flags'] == 510
    for field in ('outer_target_scored', 'board_accessed', 'arm_exported', 'control_enabled'):
        assert not r[field]
    audited = {'passed': True, 'states_checked': 210, 'new_fits_checked': 180,
        'maps_checked': 3, 'predictions_checked': total, 'source_normalization_checked': True,
        'person_seed_appearance_weighting_checked': True, 'co_primary_gates_and_coverage_checked': True,
        'baseline_predictions_byte_array_identical': True, 'unique_validation_people': 28,
        'source_fit_metrics_checked': True, 'outer_exclusions_checked': True,
        'results_sha256': digest(RUN/'results.json'), 'script_sha256': digest(Path(__file__)),
        'outer_target_scored': False, 'at_local': datetime.now().isoformat()}
    target.write_text(json.dumps(audited, indent=2), encoding='utf-8')
    print(json.dumps(audited, indent=2))


if __name__ == '__main__':
    main()

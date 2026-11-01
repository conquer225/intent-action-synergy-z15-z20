"""Fixed-source comparison of affine and restricted nonlinear readouts."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import time

import mi_time_frequency_diagnostic as prior
import verify_mi_logcov_stabilized as solver
import numpy as np
from sklearn.kernel_approximation import RBFSampler
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_readout_source_diagnostic_20261002'
PROTOCOL = HERE / 'mi_readout_protocol.json'
METHODS = ('LINEAR', 'LINEAR_PROJECTED', 'LINEAR_RFF')
SOURCES = ('mi_readout_diagnostic.py', 'mi_readout_protocol.json', 'MI_READOUT_PLAN.md',
           'test_mi_readout.py', 'audit_mi_readout.py', 'report_mi_readout.py')
read, save, digest = prior.read, prior.save, prior.digest


def sampler(seed):
    return RBFSampler(gamma=1/72, n_components=128, random_state=seed).fit(np.zeros((1, 36)))


def random_map(seed, alternate=False):
    if not alternate:
        fitted = sampler(seed)
        return fitted.random_weights_, fitted.random_offset_
    rng = np.random.RandomState(seed)
    return rng.normal(size=(36, 128))/6, rng.uniform(0, 2*np.pi, 128)


def auxiliary(z, method, seed, alternate=False):
    z = np.asarray(z, dtype=np.float64)
    if z.ndim != 2 or z.shape[1] != 36 or not len(z) or not np.isfinite(z).all():
        raise ValueError('Finite nonempty36-column input required')
    if method not in METHODS[1:] or seed not in (42, 43, 44):
        raise ValueError('Declared augmented method and seed required')
    if not alternate and method == 'LINEAR_RFF':
        return sampler(seed).transform(z)
    weights, offset = random_map(seed, alternate)
    projection = np.einsum('ij,jk->ik', z, weights) if alternate else z @ weights
    if method == 'LINEAR_PROJECTED':
        return projection/np.sqrt(128)
    return np.exp(1j*(projection+offset)).real*np.sqrt(2/128)


def augmented_fit(zfit, method, seed, alternate=False):
    extra = auxiliary(zfit, method, seed, alternate)
    mean = extra.mean(0)
    energy = float(np.mean(np.sum((extra-mean)**2, axis=1)))
    if not np.isfinite(energy) or energy <= 1e-12:
        raise ValueError('Degenerate auxiliary block; no imputation')
    scale = np.sqrt(18/energy)
    return np.column_stack((zfit/np.sqrt(2), (extra-mean)*scale)), mean, scale


def augmented_apply(z, method, seed, mean, scale, alternate=False):
    mean = np.asarray(mean)
    if mean.shape != (128,) or not np.isfinite(mean).all() or not np.isfinite(scale) or scale <= 0:
        raise ValueError('Finite source-fitted block statistics required')
    extra = auxiliary(z, method, seed, alternate)
    return np.column_stack((z/np.sqrt(2), (extra-mean)*scale))


def method_seeds(method, protocol):
    return [protocol['linear_seed_sentinel']] if method == 'LINEAR' else protocol['seeds']


def case_path(output, outer_person, method, seed, folder='models'):
    return output/folder/f'outer{outer_person:02d}_{method}_s{seed}.npz'


def fit_metrics(labels, predictions, people):
    rows = []
    for person in sorted(set(people)):
        keep = people == person
        ba, f1, _ = prior.prior_math.metric(labels[keep], predictions[keep])
        rows.append({'person': int(person), 'ba': ba, 'macro_f1': f1})
    return {'mean_person_ba': float(np.mean([row['ba'] for row in rows])), 'people': rows}


def source_data(protocol):
    for relative, expected in protocol['input_sha256'].items():
        if digest(HERE/relative) != expected:
            raise ValueError('Frozen input changed: '+relative)
    original = HERE/protocol['original_run']
    old_protocol = read(original/'protocol.json')
    assert old_protocol['participants'] == protocol['participants']
    assert old_protocol['channels'] == protocol['channels']
    with np.load(original/'statistics.npz', allow_pickle=False) as stored:
        stats = {key: stored[key].copy() for key in ('subjects', 'labels', 'order')}
    features = np.load(HERE/protocol['baseline_feature_cache'], allow_pickle=False)
    assert features.shape == (6080, 36) and np.isfinite(features).all()
    manifest = read(original/'trial_manifest.json')
    assert len(manifest) == 6080 and sum(r['voltage_bad'] or r['emg_bad'] for r in manifest) == 515
    np.testing.assert_array_equal(stats['subjects'], [r['subject'] for r in manifest])
    np.testing.assert_array_equal(stats['labels'], [r['label'] for r in manifest])
    np.testing.assert_array_equal(stats['order'], [r['original_order'] for r in manifest])
    folds = read(original/'fold_manifest.json')
    assert [fold['target'] for fold in folds] == protocol['participants']
    for fold in folds:
        prior.source_indices(fold, stats['subjects'])
    return features, stats, folds, manifest


def state_values(features, state, method, seed, alternate=False):
    z = (features-state['mean'])/state['scale']
    if method == 'LINEAR':
        assert state['factor'] == 1
        return z
    return augmented_apply(z, method, seed, state['aux_mean'], state['aux_scale'], alternate)


def prepare(output):
    protocol = read(PROTOCOL)
    features, stats, folds, _ = source_data(protocol)
    baseline = HERE/protocol['baseline_run']
    old_verification = read(baseline/'verification.json')
    old_audit = read(baseline/'integer_count_audit.json')
    assert old_verification['passed'] and old_audit['passed']
    assert old_verification['results_sha256'] == old_audit['results_sha256'] == digest(baseline/'results.json')
    output.mkdir(parents=True, exist_ok=False)
    for folder in ('models', 'maps', 'code_snapshot'):
        (output/folder).mkdir()
    inherited = read(baseline/'lock.json')['source_sha256']
    sources = list(dict.fromkeys([HERE/name for name in SOURCES]+[Path(name) for name in inherited]))
    for path in sources:
        shutil.copy2(path, output/'code_snapshot'/path.name)
    save(output/'protocol.json', protocol)
    save(output/'source_fold_manifest.json', [{**fold,
        'fit_indices': prior.source_indices(fold, stats['subjects'])[0].tolist(),
        'validation_indices': prior.source_indices(fold, stats['subjects'])[1].tolist()} for fold in folds])
    save(output/'lock.json', {'at_local': datetime.now().isoformat(),
        'source_sha256': {str(path): digest(path) for path in sources},
        'input_sha256': {str(HERE/name): expected for name, expected in protocol['input_sha256'].items()},
        'source_fold_manifest_sha256': digest(output/'source_fold_manifest.json'),
        'formal_package_sha256': digest(prior.prior_math.FROZEN), 'outer_target_scored': False})
    for seed in protocol['seeds']:
        weights, offset = random_map(seed)
        independent = random_map(seed, alternate=True)
        np.testing.assert_allclose(weights, independent[0], rtol=1e-15, atol=1e-15)
        np.testing.assert_array_equal(offset, independent[1])
        np.savez_compressed(output/'maps'/f'seed{seed}.npz', weights=weights, offset=offset)
    old_freeze = read(baseline/'source_freeze.json')
    with threadpool_limits(limits=1):
        for fold in folds:
            fit, _ = prior.source_indices(fold, stats['subjects'])
            source = prior.model_path(baseline, fold, 'WHOLE')
            assert digest(source) == old_freeze['files'][str(source)]
            old_meta = read(source.with_suffix('.json'))
            assert old_meta['C'] == .1 and old_meta['dimensions'] == 36
            assert not old_meta['source_validation_used_for_selection']
            destination = case_path(output, fold['target'], 'LINEAR', 0)
            shutil.copy2(source, destination)
            with np.load(destination, allow_pickle=False) as state:
                np.testing.assert_array_equal(state['fit_indices'], fit)
                zfit = state_values(features[fit], state, 'LINEAR', 0)
                predictions = (zfit@state['coef']+state['intercept'] > 0).astype(int)
            save(destination.with_suffix('.json'), {'outer_person': fold['target'], 'method': 'LINEAR',
                'seed': 0, 'C': .1, 'dimensions': 36, 'new_fit': False, 'reused_source': str(source),
                'reused_source_sha256': digest(source), 'source_validation_used_for_selection': False,
                'outer_target_scored': False, 'source_fit_metrics': fit_metrics(stats['labels'][fit], predictions, stats['subjects'][fit])})
    save(output/'map_freeze.json', {'at_local': datetime.now().isoformat(),
        'files': {str(path): digest(path) for path in sorted((output/'maps').glob('*.npz'))},
        'data_values_used_for_map_fit': False, 'labels_used_for_map_fit': False})
    print('READOUT_PREPARED', 30, 180, flush=True)


def load(output):
    lock = read(output/'lock.json')
    for path, expected in {**lock['source_sha256'], **lock['input_sha256']}.items():
        if digest(Path(path)) != expected:
            raise ValueError('Frozen input/code changed: '+path)
    protocol = read(output/'protocol.json')
    assert protocol == read(PROTOCOL)
    features, stats, folds, manifest = source_data(protocol)
    assert digest(output/'source_fold_manifest.json') == lock['source_fold_manifest_sha256']
    declared = read(output/'source_fold_manifest.json')
    for fold, row in zip(folds, declared):
        assert all(fold[key] == row[key] for key in fold)
        fit, val = prior.source_indices(fold, stats['subjects'])
        np.testing.assert_array_equal(fit, row['fit_indices'])
        np.testing.assert_array_equal(val, row['validation_indices'])
    map_freeze = read(output/'map_freeze.json')
    assert len(map_freeze['files']) == 3
    for path, expected in map_freeze['files'].items():
        assert digest(Path(path)) == expected
    for seed in protocol['seeds']:
        weights, offset = random_map(seed)
        with np.load(output/'maps'/f'seed{seed}.npz', allow_pickle=False) as saved:
            np.testing.assert_array_equal(weights, saved['weights'])
            np.testing.assert_array_equal(offset, saved['offset'])
    return protocol, features, stats, folds, manifest


def train(output):
    if (output/'source_freeze.json').exists() or (output/'validation_access.json').exists():
        raise RuntimeError('Frozen or scored states preserved')
    p, features, stats, folds, _ = load(output)
    started = time.monotonic()
    with threadpool_limits(limits=1):
        for fold in folds:
            fit, _ = prior.source_indices(fold, stats['subjects'])
            scaler = StandardScaler().fit(features[fit])
            zfit = scaler.transform(features[fit])
            for method in METHODS[1:]:
                for seed in p['seeds']:
                    destination = case_path(output, fold['target'], method, seed)
                    if destination.exists():
                        raise RuntimeError('Partial fitting preserved')
                    values, aux_mean, aux_scale = augmented_fit(zfit, method, seed)
                    np.testing.assert_allclose(np.mean(np.sum(values**2, axis=1)), 36, rtol=5e-9, atol=5e-9)
                    fitted = prior.prior_math.fit_classifier(values, stats['labels'][fit], p['classifier']['C'], p['classifier'])
                    np.savez_compressed(destination, mean=scaler.mean_, scale=scaler.scale_,
                        aux_mean=aux_mean, aux_scale=aux_scale, coef=fitted.coef_[0],
                        intercept=fitted.intercept_[0], fit_indices=fit)
                    predictions = (fitted.decision_function(values) > 0).astype(int)
                    save(destination.with_suffix('.json'), {'outer_person': fold['target'], 'method': method,
                        'seed': seed, 'dimensions': 164, 'C': .1, 'new_fit': True,
                        'iterations': int(fitted.n_iter_[0]), 'source_validation_used_for_selection': False,
                        'outer_target_scored': False, 'source_fit_metrics': fit_metrics(stats['labels'][fit], predictions, stats['subjects'][fit])})
            print('READOUT_FIT_FOLD', fold['target'], flush=True)
    files = sorted((output/'models').iterdir())
    assert len(files) == 420
    save(output/'source_freeze.json', {'at_local': datetime.now().isoformat(), 'new_fits': 180,
        'reused_models': 30, 'total_states': 210, 'files': {str(path): digest(path) for path in files},
        'pc_new_fit_seconds': time.monotonic()-started, 'source_validation_scored': False,
        'outer_target_scored': False})


def frozen(output):
    frozen_state = read(output/'source_freeze.json')
    assert frozen_state['new_fits'] == 180 and frozen_state['total_states'] == 210
    assert not frozen_state['source_validation_scored'] and not frozen_state['outer_target_scored']
    for path, expected in frozen_state['files'].items():
        assert digest(Path(path)) == expected, path
    return frozen_state


def aggregate(appearances, seeds):
    rows = []
    for person, cases in sorted(appearances.items()):
        means = []
        for seed in seeds:
            selected = [case for case in cases if case['seed'] == seed]
            if not selected:
                raise ValueError('Every declared seed must contribute')
            means.append({'seed': seed, 'ba': float(np.mean([case['ba'] for case in selected])),
                'macro_f1': float(np.mean([case['macro_f1'] for case in selected])), 'appearances': len(selected)})
        if len({row['appearances'] for row in means}) != 1:
            raise ValueError('Seed appearances must match')
        rows.append({'person': person, 'ba': float(np.mean([row['ba'] for row in means])),
            'macro_f1': float(np.mean([row['macro_f1'] for row in means])),
            'per_seed': means, 'cases': cases})
    return rows


def direction_gate(delta, ci, weak, settings):
    return bool(np.mean(delta) >= settings['minimum_gain'] and ci[0] > settings['lower_greater_than']
                and weak >= -settings['lowest7_drop_at_most'])


def evaluate(output):
    if (output/'validation_access.json').exists():
        raise RuntimeError('Completed or partial validation preserved')
    p, features, stats, folds, manifest = load(output)
    freeze = frozen(output)
    save(output/'validation_access.json', {'at_local': datetime.now().isoformat(),
        'freeze_at': freeze['at_local'], 'source_validation_only': True, 'outer_target_scored': False})
    (output/'validation_predictions').mkdir()
    people = sorted({person for fold in folds for person in fold['validation_people']})
    assert len(people) == 28 and set(p['participants'])-set(people) == {14, 28}
    methods, hashes = {}, {}
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 28, (10000, 28))
    total = 0
    with threadpool_limits(limits=1):
        for method in METHODS:
            appearances = {person: [] for person in people}
            train_ba = {seed: [] for seed in method_seeds(method, p)}
            for fold in folds:
                _, val = prior.source_indices(fold, stats['subjects'])
                for seed in method_seeds(method, p):
                    path = case_path(output, fold['target'], method, seed)
                    with np.load(path, allow_pickle=False) as state:
                        values = state_values(features[val], state, method, seed)
                        margin = values@state['coef']+state['intercept']
                    predictions = (margin > 0).astype(int)
                    saved = case_path(output, fold['target'], method, seed, 'validation_predictions')
                    np.savez_compressed(saved, indices=val, people=stats['subjects'][val],
                        labels=stats['labels'][val], scores=margin, predictions=predictions)
                    hashes[str(saved)] = digest(saved)
                    train_ba[seed].append(read(path.with_suffix('.json'))['source_fit_metrics']['mean_person_ba'])
                    for person in fold['validation_people']:
                        keep = stats['subjects'][val] == person
                        ba, f1, confusion = prior.prior_math.metric(stats['labels'][val][keep], predictions[keep])
                        appearances[person].append({'outer_fold': fold['target'], 'seed': seed,
                            'trials': int(keep.sum()), 'ba': ba, 'macro_f1': f1, 'confusion': confusion})
                    total += len(val)
            rows = aggregate(appearances, method_seeds(method, p))
            values = np.array([row['ba'] for row in rows])
            seed_means = [float(np.mean([row['per_seed'][i]['ba'] for row in rows]))
                          for i in range(len(method_seeds(method, p)))]
            methods[method] = {'mean_person_ba': float(values.mean()), 'between_person_sd': float(values.std(ddof=1)),
                'mean_person_f1': float(np.mean([row['macro_f1'] for row in rows])),
                'mean_lowest7_ba': float(np.sort(values)[:7].mean()),
                'descriptive_person95ci': np.quantile(values[draws].mean(1), [.025, .975]).tolist(),
                'seed_mean_ba': dict(zip(method_seeds(method, p), seed_means)),
                'seed_mean_sd': float(np.std(seed_means, ddof=1)) if len(seed_means) > 1 else 0.,
                'descriptive_source_fit_mean_ba': float(np.mean(list(train_ba.values()))),
                'source_fit_seed_fold_ba': train_ba, 'per_person': rows}
    comparisons = {}
    settings = p['co_primary']+[{'candidate': pair[0], 'reference': pair[1]} for pair in p['secondary']]
    for index, setting in enumerate(settings):
        candidate, reference = setting['candidate'], setting['reference']
        delta = np.array([row['ba'] for row in methods[candidate]['per_person']])-np.array([row['ba'] for row in methods[reference]['per_person']])
        alpha = .0125 if index < 2 else .025
        ci = np.quantile(delta[draws].mean(1), [alpha, 1-alpha]).tolist()
        weak = methods[candidate]['mean_lowest7_ba']-methods[reference]['mean_lowest7_ba']
        comparisons[candidate+'_minus_'+reference] = {'co_primary': index < 2, 'mean_gain': float(delta.mean()),
            'descriptive_paired_ci': ci, 'nominal_coverage': 1-2*alpha, 'per_person_delta': delta.tolist(),
            'lowest7_mean_difference': weak, 'people_improved': int((delta > 1e-12).sum()),
            'people_declined': int((delta < -1e-12).sum()),
            'direction_gate': direction_gate(delta, ci, weak, setting) if index < 2 else False}
    unique = {index for fold in folds for index in prior.source_indices(fold, stats['subjects'])[1]}
    save(output/'results.json', {'scope': p['scope'], 'methods': methods, 'comparisons': comparisons,
        'nominate_for_later_locked_comparison': all(c['direction_gate'] for c in comparisons.values() if c['co_primary']),
        'validation_people': people, 'absent_validation_people': [14, 28], 'person_appearances_per_seed': 90,
        'unique_validation_trials': len(unique), 'unique_validation_author_flags': sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique),
        'total_predictions': total, 'prediction_sha256': hashes, 'outer_target_scored': False,
        'board_accessed': False, 'arm_exported': False, 'control_enabled': False, 'completed_at_local': datetime.now().isoformat()})
    print('READOUT_SOURCE_ONLY', {name: value['mean_person_ba'] for name, value in methods.items()}, flush=True)
    print('READOUT_DIRECTION', {name: value['direction_gate'] for name, value in comparisons.items()}, flush=True)


def verify(output):
    if (output/'verification.json').exists():
        raise RuntimeError('Completed verification preserved')
    p, features, stats, folds, _ = load(output)
    frozen(output)
    result = read(output/'results.json')
    bounds = p['verification']
    waves = np.load(HERE/p['original_run']/'waveforms.npy', allow_pickle=False)
    rebuilt = []
    feature_error = transform_error = coefficient_error = score_error = 0.
    with threadpool_limits(limits=1):
        for index, wave in enumerate(waves):
            values = prior.prior_math.independent_features(wave)
            np.testing.assert_allclose(values, features[index], rtol=bounds['feature_rtol'], atol=bounds['feature_atol'])
            feature_error = max(feature_error, float(np.max(np.abs(values-features[index]))))
            rebuilt.append(values)
        rebuilt = np.stack(rebuilt)
        solver.TRACE.clear()
        total = 0
        for fold in folds:
            fit, val = prior.source_indices(fold, stats['subjects'])
            scaler = StandardScaler().fit(rebuilt[fit])
            zfit, zval = scaler.transform(rebuilt[fit]), scaler.transform(rebuilt[val])
            for method in METHODS:
                for seed in method_seeds(method, p):
                    path = case_path(output, fold['target'], method, seed)
                    if method == 'LINEAR':
                        values, vvalues = zfit, zval
                    else:
                        values, aux_mean, aux_scale = augmented_fit(zfit, method, seed, alternate=True)
                        vvalues = augmented_apply(zval, method, seed, aux_mean, aux_scale, alternate=True)
                    beta, _ = solver.stabilized_classifier(values, stats['labels'][fit], .1)
                    with np.load(path, allow_pickle=False) as state:
                        np.testing.assert_array_equal(state['fit_indices'], fit)
                        np.testing.assert_allclose(state['mean'], scaler.mean_, rtol=5e-9, atol=5e-9)
                        np.testing.assert_allclose(state['scale'], scaler.scale_, rtol=5e-9, atol=5e-9)
                        original_values = state_values(features[fit], state, method, seed)
                        np.testing.assert_allclose(values, original_values, rtol=bounds['transform_rtol'], atol=bounds['transform_atol'])
                        transform_error = max(transform_error, float(np.max(np.abs(values-original_values))))
                        if method != 'LINEAR':
                            np.testing.assert_allclose(aux_mean, state['aux_mean'], rtol=5e-9, atol=5e-9)
                            np.testing.assert_allclose(aux_scale, state['aux_scale'], rtol=5e-9, atol=5e-9)
                        expected = np.r_[state['coef'], state['intercept']]
                        np.testing.assert_allclose(beta, expected, rtol=bounds['coefficient_rtol'], atol=bounds['coefficient_atol'])
                        coefficient_error = max(coefficient_error, float(np.max(np.abs(beta-expected))))
                    margin = vvalues@beta[:-1]+beta[-1]
                    predpath = case_path(output, fold['target'], method, seed, 'validation_predictions')
                    assert digest(predpath) == result['prediction_sha256'][str(predpath)]
                    with np.load(predpath, allow_pickle=False) as saved:
                        np.testing.assert_allclose(margin, saved['scores'], rtol=bounds['score_rtol'], atol=bounds['score_atol'])
                        np.testing.assert_array_equal((margin > 0).astype(int), saved['predictions'])
                        score_error = max(score_error, float(np.max(np.abs(margin-saved['scores']))))
                    total += len(val)
            print('READOUT_VERIFY_FOLD', fold['target'], flush=True)
    assert len(solver.TRACE) == 210 and total == result['total_predictions']
    save(output/'solver_trace.json', {'solutions': solver.TRACE, 'count': 210})
    assert digest(prior.prior_math.FROZEN) == read(output/'lock.json')['formal_package_sha256']
    save(output/'verification.json', {'passed': True, 'schur_waveforms_rebuilt': 6080,
        'independent_solutions': 210, 'predictions_recomputed': total, 'classes_exact': True,
        'max_feature_error': feature_error, 'max_transform_error': transform_error,
        'max_coefficient_error': coefficient_error, 'max_score_error': score_error,
        'max_gradient': max(row['final_gradient'] for row in solver.TRACE),
        'solutions_refined': sum(bool(row['steps']) for row in solver.TRACE),
        'solver_trace_sha256': digest(output/'solver_trace.json'), 'results_sha256': digest(output/'results.json'),
        'formal_package_unchanged': True, 'outer_target_scored': False, 'at_local': datetime.now().isoformat()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'train', 'evaluate', 'verify'))
    parser.add_argument('--output', type=Path, default=RUN)
    args = parser.parse_args()
    {'prepare': prepare, 'train': train, 'evaluate': evaluate, 'verify': verify}[args.action](args.output)

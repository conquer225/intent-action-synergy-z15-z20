"""Bounded source-only comparison of retained versus removed total energy."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import time

import mi_time_frequency_diagnostic as prior
import numpy as np
from scipy.linalg import logm
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_energy_source_diagnostic_20261002'
PROTOCOL = HERE / 'mi_energy_protocol.json'
METHODS = ('NORMALIZED', 'NORMALIZED_ENERGY', 'ABSOLUTE')
DIMENSIONS = (36, 37, 36)
SOURCES = ('mi_energy_diagnostic.py', 'mi_energy_protocol.json', 'MI_ENERGY_PLAN.md',
           'test_mi_energy.py', 'audit_mi_energy.py', 'report_mi_energy.py')
read, save, digest = prior.read, prior.save, prior.digest
model_path, prediction_path = prior.model_path, prior.prediction_path
source_indices, scores = prior.source_indices, prior.scores
DIAGONAL = prior.prior_math.DIAGONAL


def schur_vector(covariance):
    matrix = logm(covariance)
    if np.iscomplexobj(matrix):
        if np.max(np.abs(matrix.imag)) > 1e-10:
            raise ValueError('Unexpected complex SPD logarithm')
        matrix = matrix.real
    vector = matrix[prior.prior_math.UPPER].copy()
    vector[prior.prior_math.UPPER[0] != prior.prior_math.UPPER[1]] *= np.sqrt(2)
    return vector


def features(wave, normalized=None, alternate=False):
    wave = np.asarray(wave, dtype=np.float64)
    if wave.shape != (8, 500) or not np.isfinite(wave).all():
        raise ValueError('Finite fixed8 completed500sample waveform required')
    prior.prior_math.normalized_covariance(wave.T, expected_samples=500)
    if alternate:
        covariance = np.cov(wave)
        trace = float(np.trace(covariance))
        shape = schur_vector(covariance/trace + .05*np.eye(8)/8)
        absolute = schur_vector(covariance + .05*trace*np.eye(8)/8)
    else:
        trace = float(np.var(wave, axis=1, ddof=1).sum())
        shape = prior.prior_math.log_features(wave) if normalized is None else np.asarray(normalized).copy()
        if shape.shape != (36,) or not np.isfinite(shape).all():
            raise ValueError('Finite36-dimensional cached shape required')
        absolute = shape.copy()
        absolute[DIAGONAL] += np.log(trace)
    if not np.isfinite(trace) or trace <= 1e-12:
        raise ValueError('Finite nondegenerate covariance trace required')
    result = {'NORMALIZED': shape, 'NORMALIZED_ENERGY': np.r_[shape, np.log(trace)], 'ABSOLUTE': absolute}
    if any(result[m].shape != (d,) or not np.isfinite(result[m]).all() for m, d in zip(METHODS, DIMENSIONS)):
        raise ValueError('Complete finite declared features required; no imputation')
    return result


def primary_gate(gain, lower, weakest_difference, gate):
    return bool(gain >= gate['gain_at_least'] and lower > gate['descriptive_paired_lower_greater_than']
                and weakest_difference >= -gate['lowest7_mean_drop_at_most'])


def prepare(output):
    p = read(PROTOCOL)
    stats, waves, folds, _ = prior.scope(p)
    baseline = HERE/p['baseline_run']
    prior.frozen(baseline)
    assert read(baseline/'verification.json')['passed'] and read(baseline/'integer_count_audit.json')['passed']
    old_features = np.load(HERE/p['baseline_feature_cache'], allow_pickle=False)
    assert old_features.shape == (6080, 36)
    output.mkdir(parents=True, exist_ok=False)
    (output/'models').mkdir()
    (output/'code_snapshot').mkdir()
    paths = list(dict.fromkeys([HERE/name for name in SOURCES] +
                              [Path(name) for name in read(baseline/'lock.json')['source_sha256']]))
    for path in paths:
        shutil.copy2(path, output/'code_snapshot'/path.name)
    save(output/'protocol.json', p)
    save(output/'source_fold_manifest.json', [{**fold,
        'fit_indices': source_indices(fold, stats['subjects'])[0].tolist(),
        'validation_indices': source_indices(fold, stats['subjects'])[1].tolist()} for fold in folds])
    save(output/'lock.json', {'at_local': datetime.now().isoformat(),
        'source_sha256': {str(path): digest(path) for path in paths},
        'input_sha256': {str(HERE/path): expected for path, expected in p['input_sha256'].items()},
        'source_fold_manifest_sha256': digest(output/'source_fold_manifest.json'),
        'formal_package_sha256': digest(prior.prior_math.FROZEN),
        'outer_target_scored': False, 'board_accessed': False})
    rows = {method: [] for method in METHODS}
    max_scale_identity_error = 0.
    with threadpool_limits(limits=1):
        for i, wave in enumerate(waves):
            values = features(wave, old_features[i])
            scaled = features(wave.astype(np.float64)*2)
            for method in METHODS:
                expected = values[method].copy()
                if method == 'NORMALIZED_ENERGY':
                    expected[-1] += np.log(4)
                elif method == 'ABSOLUTE':
                    expected[DIAGONAL] += np.log(4)
                np.testing.assert_allclose(scaled[method], expected, rtol=5e-9, atol=5e-9)
                max_scale_identity_error = max(max_scale_identity_error, float(np.max(np.abs(scaled[method]-expected))))
                rows[method].append(values[method])
            if (i+1) % 800 == 0:
                print('ENERGY_FEATURES', i+1, flush=True)
    np.savez_compressed(output/'features.npz', **{m: np.stack(rows[m]) for m in METHODS})
    save(output/'feature_audit.json', {'rows': 6080, 'dimensions': dict(zip(METHODS, DIMENSIONS)),
        'features_sha256': digest(output/'features.npz'), 'normalized_byte_identical': True,
        'all6080_scale_identity_probes': True, 'max_scale_identity_error': max_scale_identity_error,
        'stateless_label_free': True, 'outer_target_scored': False})
    print('ENERGY_PREPARED 60new fits/30reused models', flush=True)


def load(output):
    lock = read(output/'lock.json')
    for path, expected in {**lock['source_sha256'], **lock['input_sha256']}.items():
        if digest(path) != expected:
            raise ValueError('Frozen source/input changed: '+path)
    p = read(output/'protocol.json')
    assert p == read(PROTOCOL)
    stats, waves, folds, manifest = prior.scope(p)
    assert digest(output/'source_fold_manifest.json') == lock['source_fold_manifest_sha256']
    for fold, row in zip(folds, read(output/'source_fold_manifest.json')):
        assert all(row[key] == fold[key] for key in fold)
        fit, val = source_indices(fold, stats['subjects'])
        np.testing.assert_array_equal(row['fit_indices'], fit)
        np.testing.assert_array_equal(row['validation_indices'], val)
    assert digest(output/'features.npz') == read(output/'feature_audit.json')['features_sha256']
    with np.load(output/'features.npz', allow_pickle=False) as cache:
        arrays = {m: cache[m].copy() for m in METHODS}
    for method, dimension in zip(METHODS, DIMENSIONS):
        assert arrays[method].shape == (6080, dimension) and np.isfinite(arrays[method]).all()
    return p, stats, waves, folds, manifest, arrays


def fit_mean(labels, predictions, people):
    return float(np.mean([prior.prior_math.metric(labels[people == person], predictions[people == person])[0]
                          for person in sorted(set(people))]))


def train(output):
    if (output/'source_freeze.json').exists() or (output/'validation_access.json').exists():
        raise RuntimeError('Frozen or scored states preserved')
    p, stats, _, folds, _, arrays = load(output)
    baseline = HERE/p['baseline_run']
    prior.frozen(baseline)
    started = time.monotonic()
    for fold in folds:
        fit, _ = source_indices(fold, stats['subjects'])
        for method in METHODS:
            path = model_path(output, fold, method)
            if path.exists():
                raise RuntimeError('Partial fitting preserved')
            if method == 'NORMALIZED':
                original = prior.model_path(baseline, fold, 'WHOLE')
                shutil.copy2(original, path)
                with np.load(path, allow_pickle=False) as state:
                    iterations = read(original.with_suffix('.json'))['iterations']
                    margin = scores(state, arrays[method][fit])
            else:
                scaler = StandardScaler().fit(arrays[method][fit])
                zfit = scaler.transform(arrays[method][fit])
                classifier = prior.prior_math.fit_classifier(zfit, stats['labels'][fit], p['classifier']['C'], p['classifier'])
                np.savez_compressed(path, mean=scaler.mean_, scale=scaler.scale_, factor=1.,
                    coef=classifier.coef_[0], intercept=classifier.intercept_[0], fit_indices=fit)
                margin = classifier.decision_function(zfit)
                iterations = int(classifier.n_iter_[0])
            save(path.with_suffix('.json'), {'outer_person': fold['target'], 'method': method,
                'dimensions': arrays[method].shape[1], 'C': p['classifier']['C'], 'iterations': iterations,
                'reused_baseline': method == 'NORMALIZED',
                'source_fit_mean_person_ba': fit_mean(stats['labels'][fit], (margin>0).astype(int), stats['subjects'][fit]),
                'source_validation_used_for_selection': False, 'outer_target_scored': False})
        print('ENERGY_FIT_FOLD', fold['target'], flush=True)
    files = sorted((output/'models').iterdir())
    assert len(files) == 180
    save(output/'source_freeze.json', {'at_local': datetime.now().isoformat(), 'new_fits': 60,
        'reused_models': 30, 'total_states': 90, 'files': {str(path): digest(path) for path in files},
        'pc_fit_seconds': time.monotonic()-started, 'source_validation_scored': False, 'outer_target_scored': False})


def frozen(output):
    freeze = read(output/'source_freeze.json')
    assert freeze['new_fits'] == 60 and freeze['reused_models'] == 30 and freeze['total_states'] == 90
    assert not freeze['source_validation_scored'] and not freeze['outer_target_scored']
    for path, expected in freeze['files'].items():
        if digest(path) != expected:
            raise ValueError('Frozen model changed: '+path)
    return freeze


def evaluate(output):
    if (output/'validation_access.json').exists():
        raise RuntimeError('Scored or partial validation preserved')
    p, stats, _, folds, manifest, arrays = load(output)
    freeze = frozen(output)
    save(output/'validation_access.json', {'at_local': datetime.now().isoformat(), 'freeze_at': freeze['at_local'],
        'source_validation_only': True, 'outer_target_scored': False})
    (output/'validation_predictions').mkdir()
    for fold in folds:
        _, val = source_indices(fold, stats['subjects'])
        for method in METHODS:
            with np.load(model_path(output, fold, method), allow_pickle=False) as state:
                margin = scores(state, arrays[method][val])
            np.savez_compressed(prediction_path(output, fold, method), indices=val,
                people=stats['subjects'][val], labels=stats['labels'][val], scores=margin, predictions=(margin>0).astype(int))
    summarize(output, p, stats, folds, manifest)


def summarize(output, p, stats, folds, manifest):
    people = sorted({person for fold in folds for person in fold['validation_people']})
    assert len(people) == 28 and set(p['participants'])-set(people) == {14, 28}
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 28, (p['bootstrap']['draws'], 28))
    methods, hashes = {}, {}
    for method in METHODS:
        appearances = {person: [] for person in people}
        for fold in folds:
            path = prediction_path(output, fold, method)
            hashes[str(path)] = digest(path)
            with np.load(path, allow_pickle=False) as saved:
                for person in fold['validation_people']:
                    keep = saved['people'] == person
                    ba, f1, matrix = prior.prior_math.metric(saved['labels'][keep], saved['predictions'][keep])
                    appearances[person].append({'outer_fold': fold['target'], 'trials': int(keep.sum()),
                        'ba': ba, 'macro_f1': f1, 'confusion': matrix})
        rows = prior.average_appearances(appearances)
        values = np.array([row['ba'] for row in rows])
        methods[method] = {'mean_person_ba': float(values.mean()), 'between_person_sd': float(values.std(ddof=1)),
            'mean_lowest7_ba': float(np.sort(values)[:7].mean()),
            'mean_person_f1': float(np.mean([row['macro_f1'] for row in rows])),
            'descriptive_person95ci': np.quantile(values[draws].mean(1), [.025, .975]).tolist(),
            'descriptive_source_fit_mean_ba': float(np.mean([read(model_path(output, f, method).with_suffix('.json'))['source_fit_mean_person_ba'] for f in folds])),
            'per_person': rows}
    comparisons = {}
    for i, (candidate, reference) in enumerate([[p['primary_candidate'], p['primary_reference']]]+p['secondary_comparisons']):
        delta = np.array([row['ba'] for row in methods[candidate]['per_person']])-np.array([row['ba'] for row in methods[reference]['per_person']])
        ci = np.quantile(delta[draws].mean(1), [.025, .975]).tolist()
        weak = methods[candidate]['mean_lowest7_ba']-methods[reference]['mean_lowest7_ba']
        comparisons[candidate+'_minus_'+reference] = {'primary': i == 0, 'mean_gain': float(delta.mean()),
            'descriptive_paired_ci': ci, 'per_person_delta': delta.tolist(), 'lowest7_mean_difference': weak,
            'people_improved': int((delta>1e-12).sum()), 'people_declined': int((delta< -1e-12).sum()),
            'direction_gate': bool(i == 0 and primary_gate(delta.mean(), ci[0], weak, p['direction_gate']))}
    unique = {index for fold in folds for index in source_indices(fold, stats['subjects'])[1]}
    count = sum(len(source_indices(fold, stats['subjects'])[1]) for fold in folds)
    save(output/'results.json', {'scope': p['scope'], 'methods': methods, 'comparisons': comparisons,
        'validation_people': people, 'absent_validation_people': [14, 28], 'person_appearances': 90,
        'unique_validation_trials': len(unique), 'predictions_per_method': count, 'total_predictions': count*3,
        'unique_validation_author_flags': sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique),
        'prediction_sha256': hashes, 'outer_target_scored': False, 'board_accessed': False,
        'arm_exported': False, 'control_enabled': False, 'completed_at_local': datetime.now().isoformat()})
    print('ENERGY_SOURCE_VALIDATION_ONLY', {m: v['mean_person_ba'] for m, v in methods.items()}, flush=True)
    print('ENERGY_PRIMARY', comparisons['NORMALIZED_ENERGY_minus_NORMALIZED'], flush=True)


def verify(output):
    if (output/'verification.json').exists():
        raise RuntimeError('Existing verification preserved')
    p, stats, waves, folds, _, arrays = load(output)
    frozen(output)
    result = read(output/'results.json')
    bounds = p['verification']
    rows = {m: [] for m in METHODS}
    max_feature = 0.
    with threadpool_limits(limits=1):
        for i, wave in enumerate(waves):
            alternate = features(wave, alternate=True)
            for method in METHODS:
                np.testing.assert_allclose(alternate[method], arrays[method][i], rtol=bounds['feature_rtol'], atol=bounds['feature_atol'])
                max_feature = max(max_feature, float(np.max(np.abs(alternate[method]-arrays[method][i]))))
                rows[method].append(alternate[method])
            if (i+1) % 800 == 0:
                print('ENERGY_SCHUR', i+1, flush=True)
    alternate = {m: np.stack(values) for m, values in rows.items()}
    prior.independent_solver.TRACE.clear()
    total, max_coefficient, max_score = 0, 0., 0.
    for fold in folds:
        fit, val = source_indices(fold, stats['subjects'])
        for method in METHODS:
            scaler = StandardScaler().fit(alternate[method][fit])
            beta, _ = prior.independent_solver.stabilized_classifier(scaler.transform(alternate[method][fit]), stats['labels'][fit], p['classifier']['C'])
            with np.load(model_path(output, fold, method), allow_pickle=False) as state:
                np.testing.assert_array_equal(state['fit_indices'], fit)
                np.testing.assert_allclose(state['mean'], scaler.mean_, rtol=5e-9, atol=5e-9)
                np.testing.assert_allclose(state['scale'], scaler.scale_, rtol=5e-9, atol=5e-9)
                assert float(state['factor']) == 1.
                expected = np.r_[state['coef'], state['intercept']]
                np.testing.assert_allclose(beta, expected, rtol=bounds['coefficient_rtol'], atol=bounds['coefficient_atol'])
                max_coefficient = max(max_coefficient, float(np.max(np.abs(beta-expected))))
            margin = scaler.transform(alternate[method][val])@beta[:-1]+beta[-1]
            path = prediction_path(output, fold, method)
            assert digest(path) == result['prediction_sha256'][str(path)]
            with np.load(path, allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['predictions'], (margin>0).astype(int))
                np.testing.assert_allclose(saved['scores'], margin, rtol=bounds['score_rtol'], atol=bounds['score_atol'])
                max_score = max(max_score, float(np.max(np.abs(margin-saved['scores']))))
            total += len(val)
        print('ENERGY_VERIFY_FOLD', fold['target'], flush=True)
    trace = prior.independent_solver.TRACE
    assert len(trace) == 90 and total == result['total_predictions'] == 54840
    save(output/'solver_trace.json', {'solutions': trace, 'count': 90})
    assert digest(prior.prior_math.FROZEN) == read(output/'lock.json')['formal_package_sha256']
    save(output/'verification.json', {'passed': True, 'schur_waveforms_rebuilt': 6080,
        'log_matrices_rebuilt': 12160, 'independent_solutions': 90, 'predictions_recomputed': total,
        'classes_exact': True, 'max_feature_error': max_feature, 'max_coefficient_error': max_coefficient,
        'max_score_error': max_score, 'max_gradient': max(row['final_gradient'] for row in trace),
        'solutions_refined': sum(bool(row['steps']) for row in trace),
        'solver_trace_sha256': digest(output/'solver_trace.json'), 'results_sha256': digest(output/'results.json'),
        'outer_target_scored': False, 'formal_package_unchanged': True, 'at_local': datetime.now().isoformat()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'train', 'evaluate', 'verify'))
    parser.add_argument('--output', type=Path, default=RUN)
    args = parser.parse_args()
    {'prepare': prepare, 'train': train, 'evaluate': evaluate, 'verify': verify}[args.action](args.output)

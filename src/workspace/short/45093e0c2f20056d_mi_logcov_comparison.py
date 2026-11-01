"""Source-only fixed8 log covariance, bounded original30 experiment."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import time
import warnings

from mi_bn_trainonly import load as load_bn, check_frozen as frozen_bn, calibrated_path
from mi_person_transfer_diagnostic import read, save, digest, metric, source_model, old_checkpoint, prediction
from mi_comparison_models import configure_torch, normalized_tensor, network_logits
from mi_model_comparison import save_prediction, FROZEN
from mi_spatial import normalized_covariance
import cyton_covariance
import mi_spatial
import mi_features
import numpy as np
from scipy.linalg import logm
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / 'output/mi_logcov_sourceonly_20261002'
PROTOCOL = HERE / 'mi_logcov_protocol.json'
NEW = ('LOGCOV_FULL_LR', 'LOGCOV_DIAG_LR')
UPPER = np.triu_indices(8)
DIAGONAL = np.flatnonzero(UPPER[0] == UPPER[1])
SOURCES = ('mi_logcov_comparison.py', 'mi_logcov_protocol.json', 'MI_LOGCOV_PLAN.md',
    'test_mi_logcov.py', 'audit_mi_logcov.py', 'report_mi_logcov.py',
    'mi_bn_trainonly.py', 'mi_person_transfer_diagnostic.py', 'mi_comparison_models.py',
    'mi_model_comparison.py', 'audit_mi_person_transfer_counts.py')


def log_features(wave):
    wave = np.asarray(wave, dtype=np.float64)
    if wave.shape != (8, 500):
        raise ValueError('Exact eight-channel500-sample input required')
    section = wave.T
    normalized_covariance(section, expected_samples=500)  # Existing finite/flat guard.
    centered = section - section.mean(0)
    trace = float(np.sum(centered * centered) / 499)
    full = cyton_covariance.log_covariance(section / np.sqrt(trace))
    if full.shape != (36,) or not np.isfinite(full).all():
        raise ValueError('Finite36-dimensional log matrix required')
    return full


def independent_features(wave):
    section = np.asarray(wave, dtype=np.float64).T
    centered = section - section.mean(0)
    covariance = centered.T @ centered / (len(section)-1)
    covariance /= np.trace(covariance)
    regularized = covariance + .05 * np.eye(8) / 8
    matrix = logm(regularized)
    if np.iscomplexobj(matrix):
        if np.max(np.abs(matrix.imag)) > 1e-10:
            raise ValueError('Unexpected complex logarithm of SPD covariance')
        matrix = matrix.real
    vector = matrix[UPPER].copy()
    vector[UPPER[0] != UPPER[1]] *= np.sqrt(2)
    return vector


def source_indices(fold, subjects):
    fit = np.flatnonzero(np.isin(subjects, fold['fit_people']))
    val = np.flatnonzero(np.isin(subjects, fold['validation_people']))
    if (len(fold['fit_people']) != 26 or len(fold['validation_people']) != 3
            or set(fold['fit_people']) & set(fold['validation_people'])
            or fold['person'] in set(subjects[fit]) | set(subjects[val])
            or set(fit) & set(val)):
        raise ValueError('Exact26 source fit/3 source validation/target separation required')
    return fit, val


def fold_manifest(cases, subjects, order, participants):
    folds = []
    for person in participants:
        own = [c for c in cases if c['person'] == person]
        if [c['seed'] for c in own] != [42, 43, 44]:
            raise ValueError('Original three reference cases required')
        source = own[0]['original_source_fold']
        if any(c['original_source_fold'] != source or c['test'] != own[0]['test'] for c in own):
            raise ValueError('Reference folds differ between seeds')
        fold = {'person': person, 'fit_people': source['fit_people'],
                'validation_people': source['validation_people'], 'test': own[0]['test']}
        fit, val = source_indices(fold, subjects)
        np.testing.assert_array_equal(fold['test'], np.flatnonzero((subjects == person) & (order >= 120)))
        fold.update(fit_indices=fit.tolist(), validation_indices=val.tolist())
        folds.append(fold)
    return folds


def fit_classifier(z, labels, c, settings):
    with warnings.catch_warnings(), threadpool_limits(limits=1):
        warnings.simplefilter('error', ConvergenceWarning)
        model = LogisticRegression(C=c, solver=settings['solver'], tol=settings['tol'],
            max_iter=settings['max_iter'], penalty='l2', fit_intercept=True,
            class_weight=None, warm_start=False).fit(z, labels)
    np.testing.assert_array_equal(model.classes_, [0, 1])
    return model


def logistic_terms(beta, z, labels, c):
    w, b = beta[:-1], beta[-1]
    margins = z @ w + b
    probabilities = expit(margins)
    residual = probabilities - labels
    objective = float(np.sum(np.logaddexp(0, margins) - labels * margins) + w @ w / (2*c))
    gradient = np.r_[z.T @ residual + w/c, residual.sum()]
    weight = probabilities * (1-probabilities)
    hessian = np.empty((len(beta), len(beta)))
    hessian[:-1, :-1] = (z.T * weight) @ z + np.eye(z.shape[1])/c
    hessian[:-1, -1] = z.T @ weight
    hessian[-1, :-1] = hessian[:-1, -1]
    hessian[-1, -1] = weight.sum()
    return objective, gradient, hessian


def independent_classifier(z, labels, c):
    with threadpool_limits(limits=1):
        result = minimize(lambda b: logistic_terms(b, z, labels, c)[0], np.zeros(z.shape[1]+1),
            jac=lambda b: logistic_terms(b, z, labels, c)[1],
            hess=lambda b: logistic_terms(b, z, labels, c)[2], method='trust-exact',
            options={'gtol': 1e-7, 'maxiter': 200})
        gradient = float(np.max(np.abs(logistic_terms(result.x, z, labels, c)[1])))
    if not np.isfinite(result.x).all() or gradient > 1e-6:
        raise ValueError(f'Independent optimizer did not reach declared gradient bound: {gradient}')
    return result.x, gradient


def validation_history(coefficients, intercepts, zval, labels, subjects, people, cs):
    history = []
    for i, c in enumerate(cs):
        scores = zval @ coefficients[i] + intercepts[i]
        rows = []
        for person in people:
            keep = subjects == person
            ba, f1, matrix = metric(labels[keep], (scores[keep] > 0).astype(int))
            rows.append({'person': person, 'ba': ba, 'macro_f1': f1, 'confusion': matrix})
        history.append({'C': c, 'mean_person_ba': float(np.mean([r['ba'] for r in rows])), 'per_person': rows})
    return int(np.argmax([r['mean_person_ba'] for r in history])), history


def feature_columns(method):
    if method == NEW[0]:
        return np.arange(36)
    if method == NEW[1]:
        return DIAGONAL
    raise ValueError('Unknown new feature branch')


def checkpoint(output, fold, method):
    return output / 'models' / f's{fold["person"]:02d}_{method}.npz'


def new_scores(state, full):
    columns = state['columns']
    z = (full[:, columns] - state['mean']) / state['scale']
    i = int(state['selected_index'])
    return z @ state['coefficients'][i] + state['intercepts'][i]


def prepare(output):
    p = read(PROTOCOL)
    prior = HERE / p['prior_run']
    pp, old, stats, waves, cases = load_bn(prior)
    frozen_bn(prior)
    if digest(prior / 'results.json') != p['prior_results_sha256']:
        raise ValueError('Reference result changed')
    if p['participants'] != pp['participants'] or p['channels'] != pp['channels']:
        raise ValueError('Original scope changed')
    folds = fold_manifest(cases, stats['subjects'], stats['order'], p['participants'])
    output.mkdir(parents=True, exist_ok=False)
    (output / 'models').mkdir(); (output / 'code_snapshot').mkdir()
    paths = [HERE / name for name in SOURCES] + [Path(m.__file__) for m in (cyton_covariance, mi_spatial, mi_features)]
    for path in paths:
        shutil.copy2(path, output / 'code_snapshot' / path.name)
    save(output / 'protocol.json', p); save(output / 'fold_manifest.json', folds)
    inputs = {str(prior / name): digest(prior / name) for name in
        ('results.json', 'protocol.json', 'case_manifest.json', 'lock.json', 'source_freeze.json', 'verification.json', 'integer_count_audit.json')}
    for case in cases:
        for method in ('CROSS_ORIGINAL', 'CROSS_SOURCE_BN'):
            path = prediction(prior, case, method)
            inputs[str(path)] = digest(path)
    save(output / 'lock.json', {'declared_at_local': datetime.now().isoformat(),
        'source_sha256': {str(path): digest(path) for path in paths}, 'input_sha256': inputs,
        'fold_manifest_sha256': digest(output / 'fold_manifest.json'), 'frozen_package_sha256': digest(FROZEN),
        'raw_mat_read': False, 'board_accessed': False, 'target_person_labels_used': False})
    full = np.stack([log_features(wave) for wave in waves])
    np.save(output / 'log_features.npy', full, allow_pickle=False)
    save(output / 'feature_audit.json', {'rows': len(full), 'dimensions': 36,
        'stateless_per_trial': True, 'labels_used': False, 'feature_sha256': digest(output / 'log_features.npy'),
        'target_features_computed_before_fit': True, 'scoring_performed': False})
    print('PREPARED30 folds;240 deterministic fits;60 selected states;19840 predictions', flush=True)


def load(output):
    lock = read(output / 'lock.json')
    for path, expected in {**lock['source_sha256'], **lock['input_sha256']}.items():
        if digest(path) != expected:
            raise ValueError('Frozen source/input changed: ' + path)
    p = read(output / 'protocol.json')
    if p != read(PROTOCOL) or digest(output / 'fold_manifest.json') != lock['fold_manifest_sha256']:
        raise ValueError('Protocol/folds changed')
    _, old, stats, waves, cases = load_bn(HERE / p['prior_run'])
    frozen_bn(HERE / p['prior_run'])
    folds = fold_manifest(cases, stats['subjects'], stats['order'], p['participants'])
    if folds != read(output / 'fold_manifest.json'):
        raise ValueError('Reference split changed')
    if digest(output / 'log_features.npy') != read(output / 'feature_audit.json')['feature_sha256']:
        raise ValueError('Feature cache changed')
    full = np.load(output / 'log_features.npy', allow_pickle=False)
    if full.shape != (6080, 36) or not np.isfinite(full).all():
        raise ValueError('Complete finite feature cache required')
    return p, old, stats, waves, cases, folds, full


def train(output):
    if (output / 'source_freeze.json').exists() or (output / 'target_access.json').exists():
        raise RuntimeError('Frozen/scored models cannot be refitted')
    p, _, stats, _, _, folds, full = load(output)
    started = time.monotonic()
    cs = p['classifier']['C_in_tie_preference_order']
    for fold in folds:
        fit, val = source_indices(fold, stats['subjects'])
        for method in NEW:
            path = checkpoint(output, fold, method)
            if path.exists() or path.with_suffix('.json').exists():
                raise RuntimeError('Partial fitting preserved; diagnose before resuming')
            columns = feature_columns(method)
            scaler = StandardScaler().fit(full[fit][:, columns])
            zfit = scaler.transform(full[fit][:, columns])
            zval = scaler.transform(full[val][:, columns])
            models = [fit_classifier(zfit, stats['labels'][fit], c, p['classifier']) for c in cs]
            coef = np.stack([m.coef_[0] for m in models]); intercept = np.array([m.intercept_[0] for m in models])
            selected, history = validation_history(coef, intercept, zval, stats['labels'][val],
                stats['subjects'][val], fold['validation_people'], cs)
            for i, model in enumerate(models):
                np.testing.assert_allclose(zval @ coef[i] + intercept[i], model.decision_function(zval), rtol=1e-12, atol=1e-12)
            np.savez_compressed(path, columns=columns, mean=scaler.mean_, scale=scaler.scale_,
                coefficients=coef, intercepts=intercept, selected_index=selected,
                fit_indices=fit, validation_indices=val)
            save(path.with_suffix('.json'), {'person': fold['person'], 'method': method,
                'selected_index': selected, 'selected': history[selected], 'validation_candidates': history,
                'iterations': [int(m.n_iter_[0]) for m in models], 'target_person_labels_used': False,
                'test_scored': False, 'deterministic': True, 'dimensions': len(columns)})
        print('LOGCOV_FROZEN_FOLD', fold['person'], flush=True)
    files = sorted((output / 'models').glob('*'))
    if len(files) != 120:
        raise ValueError('Expected60 states+60metadata')
    save(output / 'source_freeze.json', {'at_local': datetime.now().isoformat(), 'selected_states': 60,
        'deterministic_fits': 240, 'files': {str(path): digest(path) for path in files},
        'elapsed_pc_seconds': time.monotonic()-started, 'target_scored': False,
        'target_person_labels_used': False, 'stateless_target_features_already_computed': True})


def frozen(output):
    freeze = read(output / 'source_freeze.json')
    if freeze['selected_states'] != 60 or freeze['deterministic_fits'] != 240 or freeze['target_scored'] or freeze['target_person_labels_used']:
        raise ValueError('Incomplete/invalid model freeze')
    for path, expected in freeze['files'].items():
        if digest(path) != expected:
            raise ValueError('Frozen model changed: ' + path)
    return freeze


def evaluate(output):
    if (output / 'results.json').exists() or (output / 'target_access.json').exists():
        raise RuntimeError('Completed or partial scoring preserved; diagnose before resuming')
    p, _, stats, _, cases, folds, full = load(output)
    freeze = frozen(output)
    save(output / 'target_access.json', {'at_local': datetime.now().isoformat(), 'freeze_at': freeze['at_local'],
        'test_previously_exposed': True, 'this_marker_is_scoring_not_first_stateless_feature_access': True})
    for fold in folds:
        indices = np.array(fold['test'])
        for method in NEW:
            with np.load(checkpoint(output, fold, method), allow_pickle=False) as state:
                scores = new_scores(state, full[indices])
            save_prediction(output, fold['person'], method, 0, indices, stats['labels'][indices], scores,
                (scores > 0).astype(int), {'deterministic_marker_not_random_seed': True, 'target_person_labels_used': False})
        for case in [c for c in cases if c['person'] == fold['person']]:
            for method in ('CROSS_ORIGINAL', 'CROSS_SOURCE_BN'):
                with np.load(prediction(HERE / p['prior_run'], case, method), allow_pickle=False) as old:
                    np.testing.assert_array_equal(old['indices'], indices)
                    save_prediction(output, case['person'], method, case['seed'], old['indices'], old['labels'],
                        old['scores'], old['predictions'], {'frozen_reference_arrays': True})
        print('LOGCOV_TEST_FOLD', fold['person'], flush=True)
    summarize(output, p, folds)


def summarize(output, p, folds):
    methods, hashes = {}, {}
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 30, (10000, 30))
    for method in p['methods']:
        rows = []
        seeds = [0] if method in NEW else p['reference_seeds']
        for fold in folds:
            repetitions = []
            for seed in seeds:
                case = {'person': fold['person'], 'seed': seed}
                path = prediction(output, case, method)
                with np.load(path, allow_pickle=False) as saved:
                    ba, f1, matrix = metric(saved['labels'], saved['predictions'])
                hashes[str(path)] = digest(path)
                repetitions.append({'seed': seed, 'ba': ba, 'macro_f1': f1, 'confusion': matrix})
            rows.append({'person': fold['person'], 'trials': len(fold['test']),
                'ba': float(np.mean([r['ba'] for r in repetitions])),
                'macro_f1': float(np.mean([r['macro_f1'] for r in repetitions])), 'per_seed': repetitions})
        values = np.array([r['ba'] for r in rows])
        methods[method] = {'mean_person_ba': float(values.mean()), 'between_person_sd': float(values.std(ddof=1)),
            'mean_lowest8_ba': float(np.sort(values)[:8].mean()), 'mean_person_f1': float(np.mean([r['macro_f1'] for r in rows])),
            'person95ci': np.quantile(values[draws].mean(1), [.025, .975]).tolist(), 'per_person': rows,
            'deterministic_new_model': method in NEW}
    comparisons = {}
    pairs = [[p['primary_candidate'], p['primary_reference']]] + p['secondary_comparisons']
    for i, (candidate, reference) in enumerate(pairs):
        delta = np.array([r['ba'] for r in methods[candidate]['per_person']])-np.array([r['ba'] for r in methods[reference]['per_person']])
        ci = np.quantile(delta[draws].mean(1), [.025, .975]).tolist()
        weak = methods[candidate]['mean_lowest8_ba']-methods[reference]['mean_lowest8_ba']
        gate = bool(i == 0 and delta.mean() >= .02 and ci[0] > 0 and weak >= -.01)
        comparisons[candidate+'_minus_'+reference] = {'primary': i == 0, 'mean_gain': float(delta.mean()),
            'paired_ci': ci, 'per_person_delta': delta.tolist(), 'lowest8_mean_difference': weak,
            'people_improved': int((delta > 1e-12).sum()), 'people_declined': int((delta < -1e-12).sum()), 'development_gate': gate}
    manifest = read(HERE / p['original_run'] / 'trial_manifest.json')
    unique = {i for fold in folds for i in fold['test']}
    save(output / 'results.json', {'scope': p['scope'], 'methods': methods, 'comparisons': comparisons,
        'scored_unique_trials': len(unique), 'scored_author_flags': sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique),
        'prediction_sha256': hashes, 'total_predictions': 19840, 'completed_at_local': datetime.now().isoformat(),
        'personal_labels_used': False, 'board_accessed': False, 'deployment_authorized': False, 'control_enabled': False})
    print({m: v['mean_person_ba'] for m, v in methods.items()}, flush=True)
    print(comparisons, flush=True)


def verify(output):
    if (output / 'verification.json').exists():
        raise RuntimeError('Existing verification preserved')
    p, old, stats, waves, cases, folds, full = load(output)
    frozen(output); configure_torch(old['compute'])
    result = read(output / 'results.json'); bounds = p['verification']
    rebuilt_features, feature_error = [], 0.
    with threadpool_limits(limits=1):
        for i, wave in enumerate(waves):
            row = independent_features(wave)
            np.testing.assert_allclose(row, full[i], rtol=bounds['feature_rtol'], atol=bounds['feature_atol'])
            feature_error = max(feature_error, float(np.max(np.abs(row-full[i]))))
            rebuilt_features.append(row)
            if (i+1) % 400 == 0:
                print('LOGCOV_SCHUR_FEATURES', i+1, flush=True)
    alternate = np.stack(rebuilt_features)
    rebuilt, predictions, coefficient_error, score_error, max_gradient = 0, 0, 0., 0., 0.
    cs = p['classifier']['C_in_tie_preference_order']
    for fold in folds:
        fit, val = source_indices(fold, stats['subjects']); indices = np.array(fold['test'])
        for method in NEW:
            columns = feature_columns(method)
            scaler = StandardScaler().fit(alternate[fit][:, columns])
            zfit = scaler.transform(alternate[fit][:, columns]); zval = scaler.transform(alternate[val][:, columns])
            beta = []
            for c in cs:
                b, gradient = independent_classifier(zfit, stats['labels'][fit], c)
                beta.append(b); max_gradient = max(max_gradient, gradient); rebuilt += 1
            beta = np.array(beta)
            with np.load(checkpoint(output, fold, method), allow_pickle=False) as state:
                np.testing.assert_array_equal(state['columns'], columns)
                np.testing.assert_array_equal(state['fit_indices'], fit); np.testing.assert_array_equal(state['validation_indices'], val)
                np.testing.assert_allclose(state['mean'], scaler.mean_, rtol=5e-9, atol=5e-9)
                np.testing.assert_allclose(state['scale'], scaler.scale_, rtol=5e-9, atol=5e-9)
                for key, expected in (('coefficients', beta[:, :-1]), ('intercepts', beta[:, -1])):
                    np.testing.assert_allclose(state[key], expected, rtol=bounds['coefficient_rtol'], atol=bounds['coefficient_atol'])
                    coefficient_error = max(coefficient_error, float(np.max(np.abs(state[key]-expected))))
                selected, history = validation_history(beta[:, :-1], beta[:, -1], zval, stats['labels'][val],
                    stats['subjects'][val], fold['validation_people'], cs)
                meta = read(checkpoint(output, fold, method).with_suffix('.json'))
                assert selected == int(state['selected_index']) == meta['selected_index'] and history == meta['validation_candidates']
                ztest = scaler.transform(alternate[indices][:, columns])
                scores = ztest @ beta[selected, :-1] + beta[selected, -1]
            path = prediction(output, {'person': fold['person'], 'seed': 0}, method)
            assert digest(path) == result['prediction_sha256'][str(path)]
            with np.load(path, allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['predictions'], (scores > 0).astype(int))
                np.testing.assert_allclose(saved['scores'], scores, rtol=bounds['new_score_rtol'], atol=bounds['new_score_atol'])
                score_error = max(score_error, float(np.max(np.abs(saved['scores']-scores))))
            predictions += len(indices)
        for case in [c for c in cases if c['person'] == fold['person']]:
            for method in ('CROSS_ORIGINAL', 'CROSS_SOURCE_BN'):
                path = old_checkpoint(HERE / p['original_run'], case['person'], case['seed']) if method == 'CROSS_ORIGINAL' else calibrated_path(HERE / p['prior_run'], case, method)
                c, model = source_model(path)
                scores = network_logits(model, normalized_tensor(waves[indices], np.array(c['source_mean']), np.array(c['source_scale']), 'cpu'))
                predpath = prediction(output, case, method)
                assert digest(predpath) == result['prediction_sha256'][str(predpath)]
                with np.load(predpath, allow_pickle=False) as saved:
                    np.testing.assert_array_equal(saved['predictions'], scores.argmax(1))
                    np.testing.assert_allclose(saved['scores'], scores, rtol=bounds['reference_score_rtol'], atol=bounds['reference_score_atol'])
                    score_error = max(score_error, float(np.max(np.abs(saved['scores']-scores))))
                predictions += len(indices)
        print('LOGCOV_VERIFY_FOLD', fold['person'], flush=True)
    assert rebuilt == 240 and predictions == 19840
    assert digest(FROZEN) == read(output / 'lock.json')['frozen_package_sha256']
    save(output / 'verification.json', {'passed': True, 'schur_features_rebuilt': len(alternate),
        'independent_newton_solutions': rebuilt, 'all60_source_validation_selections_exact': True,
        'predictions_recomputed': predictions, 'classes_exact': True, 'max_feature_error': feature_error,
        'max_coefficient_error': coefficient_error, 'max_score_error': score_error, 'max_independent_gradient': max_gradient,
        'formal_package_unchanged': True, 'results_sha256': digest(output / 'results.json'), 'at_local': datetime.now().isoformat()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'train', 'evaluate', 'verify'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    {'prepare': prepare, 'train': train, 'evaluate': evaluate, 'verify': verify}[args.action](args.output)

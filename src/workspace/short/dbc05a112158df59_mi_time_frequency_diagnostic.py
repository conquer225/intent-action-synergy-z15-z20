"""Fixed time/frequency diagnostic on source validation only, no target scoring."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import time
import mi_logcov_comparison as prior_math  # Load Torch DLLs before SciPy on Windows.
import verify_mi_logcov_stabilized as independent_solver
import numpy as np
from scipy import fft
from scipy.linalg import logm
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_time_frequency_source_diagnostic_20261002'
PROTOCOL = HERE / 'mi_time_frequency_protocol.json'
METHODS = ('WHOLE', 'TIME2', 'FREQ2', 'TIME2_FREQ2')
DIMENSIONS = (36, 72, 72, 144)
SOURCES = ('mi_time_frequency_diagnostic.py', 'mi_time_frequency_protocol.json',
    'MI_TIME_FREQUENCY_PLAN.md', 'test_mi_time_frequency.py',
    'audit_mi_time_frequency.py', 'report_mi_time_frequency.py')
read, save, digest = prior_math.read, prior_math.save, prior_math.digest


def split_frequency(wave, alternate=False):
    values = np.asarray(wave, dtype=np.float64)
    if values.shape != (8, 500) or not np.isfinite(values).all():
        raise ValueError('Finite fixed8 completed500sample waveform required')
    module = fft if alternate else np.fft
    spectrum = module.rfft(values, axis=1, norm='ortho')
    low_mask = module.rfftfreq(500, d=1/250) < 14
    low = module.irfft(spectrum * low_mask, n=500, axis=1, norm='ortho')
    high = module.irfft(spectrum * ~low_mask, n=500, axis=1, norm='ortho')
    return low, high


def segment_log(section, parent_trace, alternate=False):
    prior_math.normalized_covariance(section, expected_samples=len(section))
    if not np.isfinite(parent_trace) or parent_trace <= 1e-12:
        raise ValueError('Nondegenerate finite parent covariance trace required')
    if not alternate:
        return prior_math.cyton_covariance.log_covariance(section / np.sqrt(parent_trace))
    centered = section - section.mean(0)
    covariance = (centered.T @ centered) / ((len(section)-1)*parent_trace)
    regularized = covariance + .05 * np.trace(covariance) * np.eye(8)/8
    matrix = logm(regularized)
    if np.iscomplexobj(matrix):
        if np.max(np.abs(matrix.imag)) > 1e-10:
            raise ValueError('Unexpected complex SPD logarithm')
        matrix = matrix.real
    vector = matrix[prior_math.UPPER].copy()
    vector[prior_math.UPPER[0] != prior_math.UPPER[1]] *= np.sqrt(2)
    return vector


def features(wave, alternate=False):
    wave = np.asarray(wave, dtype=np.float64)
    if wave.shape != (8, 500) or not np.isfinite(wave).all():
        raise ValueError('Finite8by500 required')
    centered = wave - wave.mean(1, keepdims=True)
    trace = float(np.sum(centered*centered)/499)
    low, high = split_frequency(wave, alternate)
    component = lambda w: segment_log(w.T, trace, alternate)
    result = {
        'WHOLE': component(wave),
        'TIME2': np.concatenate([component(wave[:, :250]), component(wave[:, 250:])]),
        'FREQ2': np.concatenate([component(low), component(high)]),
        'TIME2_FREQ2': np.concatenate([component(w[:, s:s+250])
            for s in (0, 250) for w in (low, high)])}
    if any(result[m].shape != (d,) or not np.isfinite(result[m]).all()
           for m, d in zip(METHODS, DIMENSIONS)):
        raise ValueError('Complete finite declared features required; no trial deletion')
    return result


def source_indices(fold, subjects):
    fit_people, val_people = fold['fit_people'], fold['validation_people']
    if (len(set(fit_people)) != 26 or len(set(val_people)) != 3
            or len(fit_people) != 26 or len(val_people) != 3
            or set(fit_people) & set(val_people)
            or fold['target'] in set(fit_people) | set(val_people)):
        raise ValueError('Exact disjoint source26/source3; outer person excluded')
    fit = np.flatnonzero(np.isin(subjects, fit_people))
    val = np.flatnonzero(np.isin(subjects, val_people))
    if not len(fit) or not len(val) or set(fit)&set(val):
        raise ValueError('Nonempty disjoint source rows required')
    return fit, val


def scope(protocol):
    for relative, expected in protocol['input_sha256'].items():
        if digest(HERE/relative) != expected:
            raise ValueError('Declared input changed: '+relative)
    original = HERE/protocol['original_run']
    source_protocol = read(original/'protocol.json')
    if source_protocol['participants'] != protocol['participants'] or source_protocol['channels'] != protocol['channels']:
        raise ValueError('Fixed people/channels changed')
    with np.load(original/'statistics.npz', allow_pickle=False) as saved:
        stats = {k: saved[k].copy() for k in ('labels', 'subjects', 'order')}
    waves = np.load(original/'waveforms.npy', allow_pickle=False)
    if waves.shape != (6080, 8, 500) or not np.isfinite(waves).all():
        raise ValueError('Exact complete original cache required')
    manifest = read(original/'trial_manifest.json')
    assert len(manifest) == 6080
    np.testing.assert_array_equal(stats['subjects'], [r['subject'] for r in manifest])
    np.testing.assert_array_equal(stats['labels'], [r['label'] for r in manifest])
    np.testing.assert_array_equal(stats['order'], [r['original_order'] for r in manifest])
    assert sum(r['voltage_bad'] or r['emg_bad'] for r in manifest) == 515
    folds = read(original/'fold_manifest.json')
    assert [f['target'] for f in folds] == protocol['participants']
    for fold in folds:
        fit, val = source_indices(fold, stats['subjects'])
        assert sorted(set(fold['fit_people']) | set(fold['validation_people']) | {fold['target']}) == protocol['participants']
    return stats, waves, folds, manifest


def prepare(output):
    p = read(PROTOCOL)
    stats, waves, folds, _ = scope(p)
    output.mkdir(parents=True, exist_ok=False)
    (output/'models').mkdir(); (output/'code_snapshot').mkdir()
    prior_lock = read(HERE/'output/mi_logcov_sourceonly_20261002/lock.json')
    source_paths = [HERE/name for name in SOURCES] + [Path(name) for name in prior_lock['source_sha256']]
    source_paths.append(Path(independent_solver.__file__))
    source_paths = list(dict.fromkeys(source_paths))
    for path in source_paths:
        shutil.copy2(path, output/'code_snapshot'/path.name)
    save(output/'protocol.json', p)
    save(output/'source_fold_manifest.json', [{**fold,
        'fit_indices': source_indices(fold, stats['subjects'])[0].tolist(),
        'validation_indices': source_indices(fold, stats['subjects'])[1].tolist()} for fold in folds])
    save(output/'lock.json', {'at_local': datetime.now().isoformat(),
        'source_sha256': {str(path): digest(path) for path in source_paths},
        'input_sha256': {str(HERE/r): h for r, h in p['input_sha256'].items()},
        'source_fold_manifest_sha256': digest(output/'source_fold_manifest.json'),
        'formal_package_sha256': digest(prior_math.FROZEN), 'outer_target_scored': False,
        'raw_mat_read': False, 'board_accessed': False})
    rows = {m: [] for m in METHODS}
    permutation_error = recovery_error = orthogonality_error = 0.
    shuffled = np.random.default_rng(20261002).permutation(500)
    with threadpool_limits(limits=1):
        for i, wave in enumerate(waves):
            values = features(wave)
            for method in METHODS:
                rows[method].append(values[method])
            low, high = split_frequency(wave)
            recovery_error = max(recovery_error, float(np.max(np.abs(low+high-wave))))
            centered = wave.astype(np.float64)-wave.mean(1, dtype=np.float64, keepdims=True)
            parent_trace = float(np.sum(centered*centered)/499)
            lc, hc = low-low.mean(1, keepdims=True), high-high.mean(1, keepdims=True)
            orthogonality_error = max(orthogonality_error, float(np.max(np.abs(lc@hc.T/499/parent_trace))))
            permuted = prior_math.log_features(wave[:, shuffled])
            np.testing.assert_allclose(permuted, values['WHOLE'], rtol=5e-9, atol=5e-9)
            permutation_error = max(permutation_error, float(np.max(np.abs(permuted-values['WHOLE']))))
            if (i+1) % 800 == 0:
                print('TF_FEATURES', i+1, flush=True)
    arrays = {m: np.stack(rows[m]) for m in METHODS}
    old_features = np.load(HERE/p['baseline_feature_cache'], allow_pickle=False)
    np.testing.assert_allclose(arrays['WHOLE'], old_features, rtol=5e-9, atol=5e-9)
    np.testing.assert_allclose(recovery_error, 0, rtol=0, atol=1e-9)
    assert orthogonality_error <= 1e-12
    np.savez_compressed(output/'features.npz', **arrays)
    save(output/'feature_audit.json', {'rows': 6080, 'dimensions': dict(zip(METHODS, DIMENSIONS)),
        'stateless_label_free': True, 'features_sha256': digest(output/'features.npz'),
        'whole_matches_previous_features': True, 'max_whole_permutation_error': permutation_error,
        'max_waveform_reconstruction_error': recovery_error,
        'max_parent_normalized_cross_covariance': orthogonality_error,
        'all6080_identity_probes_checked': True, 'outer_target_scored': False})
    print('TF_PREPARED', 30, 120, flush=True)


def load(output):
    lock = read(output/'lock.json')
    for path, expected in {**lock['source_sha256'], **lock['input_sha256']}.items():
        if digest(path) != expected:
            raise ValueError('Frozen source/input changed: '+path)
    p = read(output/'protocol.json')
    assert p == read(PROTOCOL)
    stats, waves, folds, manifest = scope(p)
    assert digest(output/'source_fold_manifest.json') == lock['source_fold_manifest_sha256']
    declared = read(output/'source_fold_manifest.json')
    for fold, row in zip(folds, declared):
        assert all(row[key] == fold[key] for key in fold)
        fit, val = source_indices(fold, stats['subjects'])
        np.testing.assert_array_equal(row['fit_indices'], fit)
        np.testing.assert_array_equal(row['validation_indices'], val)
    assert digest(output/'features.npz') == read(output/'feature_audit.json')['features_sha256']
    with np.load(output/'features.npz', allow_pickle=False) as cached:
        arrays = {m: cached[m].copy() for m in METHODS}
    for m, d in zip(METHODS, DIMENSIONS):
        assert arrays[m].shape == (6080, d) and np.isfinite(arrays[m]).all()
    return p, stats, waves, folds, manifest, arrays


def model_path(output, fold, method):
    return output/'models'/f'outer{fold["target"]:02d}_{method}.npz'


def prediction_path(output, fold, method):
    return output/'validation_predictions'/f'outer{fold["target"]:02d}_{method}.npz'


def train(output):
    if (output/'source_freeze.json').exists() or (output/'validation_access.json').exists():
        raise RuntimeError('Frozen or scored states preserved')
    p, stats, _, folds, _, arrays = load(output)
    start = time.monotonic()
    for fold in folds:
        fit, _ = source_indices(fold, stats['subjects'])
        for method in METHODS:
            path = model_path(output, fold, method)
            if path.exists():
                raise RuntimeError('Partial fitting preserved')
            values = arrays[method]
            scaler = StandardScaler().fit(values[fit])
            factor = np.sqrt(36/values.shape[1])
            zfit = scaler.transform(values[fit])*factor
            classifier = prior_math.fit_classifier(zfit, stats['labels'][fit], p['classifier']['C'], p['classifier'])
            np.savez_compressed(path, mean=scaler.mean_, scale=scaler.scale_, factor=factor,
                coef=classifier.coef_[0], intercept=classifier.intercept_[0], fit_indices=fit)
            save(path.with_suffix('.json'), {'outer_person': fold['target'], 'method': method,
                'dimensions': values.shape[1], 'C': p['classifier']['C'], 'iterations': int(classifier.n_iter_[0]),
                'source_validation_used_for_selection': False, 'outer_target_scored': False})
        print('TF_FIT_FOLD', fold['target'], flush=True)
    files = sorted((output/'models').glob('*'))
    assert len(files) == 240
    save(output/'source_freeze.json', {'at_local': datetime.now().isoformat(), 'fitted_models': 120,
        'files': {str(path): digest(path) for path in files}, 'pc_fit_seconds': time.monotonic()-start,
        'source_validation_scored': False, 'outer_target_scored': False})


def frozen(output):
    freeze = read(output/'source_freeze.json')
    assert freeze['fitted_models'] == 120 and not freeze['source_validation_scored'] and not freeze['outer_target_scored']
    for path, expected in freeze['files'].items():
        if digest(path) != expected:
            raise ValueError('Frozen model changed: '+path)
    return freeze


def scores(state, values):
    return ((values-state['mean'])/state['scale']*state['factor'])@state['coef']+state['intercept']


def average_appearances(appearances):
    return [{'person': person, 'appearances': app,
        'ba': float(np.mean([r['ba'] for r in app])),
        'macro_f1': float(np.mean([r['macro_f1'] for r in app]))}
        for person, app in sorted(appearances.items())]


def evaluate(output):
    if (output/'validation_access.json').exists():
        raise RuntimeError('Scored or partial validation preserved')
    p, stats, _, folds, manifest, arrays = load(output)
    freeze = frozen(output)
    save(output/'validation_access.json', {'at_local': datetime.now().isoformat(),
        'freeze_at': freeze['at_local'], 'source_validation_only': True, 'outer_target_scored': False})
    (output/'validation_predictions').mkdir()
    for fold in folds:
        _, val = source_indices(fold, stats['subjects'])
        for method in METHODS:
            with np.load(model_path(output, fold, method), allow_pickle=False) as state:
                margin = scores(state, arrays[method][val])
            np.savez_compressed(prediction_path(output, fold, method), indices=val,
                people=stats['subjects'][val], labels=stats['labels'][val],
                scores=margin, predictions=(margin>0).astype(int))
    summarize(output, p, stats, folds, manifest)


def summarize(output, p, stats, folds, manifest):
    people = sorted({person for f in folds for person in f['validation_people']})
    assert len(people) == 28 and set(p['participants'])-set(people) == {14, 28}
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 28, (10000, 28))
    methods, hashes = {}, {}
    for method in METHODS:
        appearances = {person: [] for person in people}
        for fold in folds:
            path = prediction_path(output, fold, method)
            hashes[str(path)] = digest(path)
            with np.load(path, allow_pickle=False) as saved:
                for person in fold['validation_people']:
                    keep = saved['people'] == person
                    ba, f1, confusion = prior_math.metric(saved['labels'][keep], saved['predictions'][keep])
                    appearances[person].append({'outer_fold': fold['target'], 'trials': int(keep.sum()),
                        'ba': ba, 'macro_f1': f1, 'confusion': confusion})
        rows = average_appearances(appearances)
        values = np.array([r['ba'] for r in rows])
        methods[method] = {'mean_person_ba': float(values.mean()), 'between_person_sd': float(values.std(ddof=1)),
            'mean_lowest7_ba': float(np.sort(values)[:7].mean()),
            'mean_person_f1': float(np.mean([r['macro_f1'] for r in rows])),
            'descriptive_person95ci': np.quantile(values[draws].mean(1), [.025, .975]).tolist(), 'per_person': rows}
    comparisons = {}
    for i, (candidate, reference) in enumerate([[p['primary_candidate'],p['primary_reference']]]+p['secondary_comparisons']):
        delta = np.array([r['ba'] for r in methods[candidate]['per_person']])-np.array([r['ba'] for r in methods[reference]['per_person']])
        ci = np.quantile(delta[draws].mean(1), [.025, .975]).tolist()
        weak = methods[candidate]['mean_lowest7_ba']-methods[reference]['mean_lowest7_ba']
        gate = p['direction_gate']
        comparisons[candidate+'_minus_'+reference] = {'primary': i == 0, 'mean_gain': float(delta.mean()),
            'descriptive_paired_ci': ci, 'per_person_delta': delta.tolist(), 'lowest7_mean_difference': weak,
            'people_improved': int((delta>1e-12).sum()), 'people_declined': int((delta< -1e-12).sum()),
            'direction_gate': bool(i == 0 and delta.mean() >= gate['gain_at_least']
                and ci[0] > gate['descriptive_paired_lower_greater_than'] and weak >= -gate['lowest7_mean_drop_at_most'])}
    unique = {idx for fold in folds for idx in source_indices(fold, stats['subjects'])[1]}
    count = sum(len(source_indices(f,stats['subjects'])[1]) for f in folds)
    save(output/'results.json', {'scope': p['scope'], 'methods': methods, 'comparisons': comparisons,
        'validation_people': people, 'absent_validation_people': [14,28], 'person_appearances': 90,
        'unique_validation_trials': len(unique), 'predictions_per_method': count, 'total_predictions': count*4,
        'unique_validation_author_flags': sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique),
        'prediction_sha256': hashes, 'outer_target_scored': False, 'board_accessed': False,
        'arm_exported': False, 'control_enabled': False, 'completed_at_local': datetime.now().isoformat()})
    print('TF_SOURCE_VALIDATION_ONLY', {m:v['mean_person_ba'] for m,v in methods.items()}, flush=True)
    print('TF_PRIMARY', comparisons['TIME2_FREQ2_minus_WHOLE'], flush=True)


def verify(output):
    if (output/'verification.json').exists():
        raise RuntimeError('Existing verification preserved')
    p, stats, waves, folds, _, arrays = load(output)
    frozen(output)
    result = read(output/'results.json'); bounds = p['verification']
    alternate = {m: [] for m in METHODS}
    max_feature = 0.
    with threadpool_limits(limits=1):
        for i, wave in enumerate(waves):
            row = features(wave, alternate=True)
            for method in METHODS:
                np.testing.assert_allclose(row[method], arrays[method][i], rtol=bounds['feature_rtol'], atol=bounds['feature_atol'])
                max_feature = max(max_feature, float(np.max(np.abs(row[method]-arrays[method][i]))))
                alternate[method].append(row[method])
            if (i+1) % 400 == 0:
                print('TF_SCHUR_FFT', i+1, flush=True)
    alternate = {m:np.stack(rows) for m,rows in alternate.items()}
    independent_solver.TRACE.clear()
    total, max_coefficient, max_score = 0, 0., 0.
    for fold in folds:
        fit, val = source_indices(fold, stats['subjects'])
        for method in METHODS:
            scaler = StandardScaler().fit(alternate[method][fit])
            factor = np.sqrt(36/alternate[method].shape[1])
            beta, _ = independent_solver.stabilized_classifier(scaler.transform(alternate[method][fit])*factor,
                stats['labels'][fit], p['classifier']['C'])
            with np.load(model_path(output,fold,method), allow_pickle=False) as state:
                np.testing.assert_array_equal(state['fit_indices'],fit)
                np.testing.assert_allclose(state['mean'],scaler.mean_,rtol=5e-9,atol=5e-9)
                np.testing.assert_allclose(state['scale'],scaler.scale_,rtol=5e-9,atol=5e-9)
                np.testing.assert_allclose(state['factor'],factor,rtol=0,atol=0)
                expected = np.r_[state['coef'],state['intercept']]
                np.testing.assert_allclose(beta, expected, rtol=bounds['coefficient_rtol'],atol=bounds['coefficient_atol'])
                max_coefficient=max(max_coefficient,float(np.max(np.abs(beta-expected))))
            margin = scaler.transform(alternate[method][val])*factor@beta[:-1]+beta[-1]
            path=prediction_path(output,fold,method)
            assert digest(path)==result['prediction_sha256'][str(path)]
            with np.load(path, allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['predictions'],(margin>0).astype(int))
                np.testing.assert_allclose(saved['scores'],margin,rtol=bounds['score_rtol'],atol=bounds['score_atol'])
                max_score=max(max_score,float(np.max(np.abs(margin-saved['scores']))))
            total+=len(val)
        print('TF_VERIFY_FOLD',fold['target'],flush=True)
    assert len(independent_solver.TRACE)==120 and total==result['total_predictions']
    save(output/'solver_trace.json',{'solutions':independent_solver.TRACE,'count':120})
    assert digest(prior_math.FROZEN)==read(output/'lock.json')['formal_package_sha256']
    save(output/'verification.json',{'passed':True,'schur_fft_waveforms_rebuilt':6080,
        'log_matrices_rebuilt':6080*9,'independent_solutions':120,'predictions_recomputed':total,
        'classes_exact':True,'max_feature_error':max_feature,'max_coefficient_error':max_coefficient,
        'max_score_error':max_score,'max_gradient':max(r['final_gradient'] for r in independent_solver.TRACE),
        'solutions_refined':sum(bool(r['steps']) for r in independent_solver.TRACE),
        'solver_trace_sha256':digest(output/'solver_trace.json'),'results_sha256':digest(output/'results.json'),
        'outer_target_scored':False,'formal_package_unchanged':True,'at_local':datetime.now().isoformat()})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','train','evaluate','verify'))
    parser.add_argument('--output',type=Path,default=RUN)
    args=parser.parse_args()
    {'prepare':prepare,'train':train,'evaluate':evaluate,'verify':verify}[args.action](args.output)

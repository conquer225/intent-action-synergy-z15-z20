"""Frozen source readout plus labeled80/40 residual: offline original30 only."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import time

from mi_person_transfer_diagnostic import (load as load_prior, frozen as frozen_prior,
    read, save, digest, features, metric, source_model, old_checkpoint, new_checkpoint,
    personal_indices, prediction, head_scores)
from mi_comparison_models import configure_torch, normalized_tensor, network_logits, torch
from mi_model_comparison import save_prediction, FROZEN
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / 'output/mi_source_residual_20261002'
PROTOCOL = HERE / 'mi_residual_protocol.json'
NEW = ('SOURCE_BOUNDED_RESIDUAL', 'SOURCE_FREE_RESIDUAL')
SOURCES = ('mi_residual_diagnostic.py', 'mi_residual_protocol.json', 'MI_RESIDUAL_PLAN.md',
    'test_mi_residual.py', 'audit_mi_residual.py', 'report_mi_residual.py',
    'mi_person_transfer_diagnostic.py', 'mi_comparison_models.py', 'mi_model_comparison.py',
    'audit_mi_person_transfer_counts.py')


def class1_probability(logits):
    logits = np.asarray(logits, dtype=np.float64)
    if logits.ndim != 2 or logits.shape[1] != 2 or not np.isfinite(logits).all():
        raise ValueError('Finite Nx2 source logits required')
    margin = logits[:, 1] - logits[:, 0]
    result = np.empty_like(margin)
    positive = margin >= 0
    result[positive] = 1 / (1 + np.exp(-margin[positive]))
    e = np.exp(margin[~positive])
    result[~positive] = e / (1 + e)
    return result


def fit_residual(z, labels, probability, alpha):
    z, labels, probability = [np.asarray(v, dtype=np.float64) for v in (z, labels, probability)]
    if (z.ndim != 2 or len(z) != len(labels) or labels.shape != probability.shape
            or set(labels) != {0, 1} or alpha <= 0 or not all(np.isfinite(v).all() for v in (z, probability))
            or np.any((probability < 0) | (probability > 1))):
        raise ValueError('Finite balanced binary training rows and positive ridge required')
    center = z.mean(0)
    x = z - center
    target = labels - probability
    mean = target.mean()
    with threadpool_limits(limits=1):
        w = x.T @ np.linalg.solve(x @ x.T + len(x) * alpha * np.eye(len(x)), target - mean)
    return w, float(mean - center @ w)


def corrected_probability(base, residual, strength, cap):
    base, residual = [np.asarray(v, dtype=np.float64) for v in (base, residual)]
    if (base.ndim != 1 or base.shape != residual.shape or not np.isfinite(base).all()
            or not np.isfinite(residual).all() or np.any((base < 0) | (base > 1))
            or not 0 <= strength <= 1 or (cap is not None and not 0 < cap <= .5)):
        raise ValueError('Finite probability/residual and declared bounds required')
    if strength == 0:
        return base.copy()
    delta = np.clip(residual, -cap, cap) if cap is not None else residual
    return np.clip(base + strength * delta, 0, 1)


def fit_validation_indices(case, subjects, order):
    fit, val, test = personal_indices(subjects, order, case['person'])
    for key, indices in (('personal_fit', fit), ('personal_validation', val), ('test', test)):
        np.testing.assert_array_equal(case[key], indices)
    return fit, val


def select_candidate(p, coefficients, intercepts, zval, pval, labels, cap):
    configs = [(None, 0.)] + [(i, strength) for strength in p['strengths_in_tie_preference_order']
                              for i in range(len(p['alphas_in_tie_preference_order']))]
    rows = []
    for i, strength in configs:
        residual = np.zeros(len(pval)) if i is None else zval @ coefficients[i] + intercepts[i]
        prob = corrected_probability(pval, residual, strength, cap)
        ba, f1, matrix = metric(labels, (prob > .5).astype(int))
        rows.append({'alpha_index': i, 'alpha': None if i is None else p['alphas_in_tie_preference_order'][i],
                     'strength': strength, 'validation_ba': ba, 'validation_f1': f1, 'confusion': matrix})
    selected = int(np.argmax([r['validation_ba'] for r in rows]))
    return selected, rows


def checkpoint(output, case, method):
    return output / 'models' / f's{case["person"]:02d}_{method}_seed{case["seed"]}.npz'


def source_path(p, case):
    prior = HERE / p['prior_run']
    return old_checkpoint(HERE / read(prior / 'protocol.json')['original_run'], case['person'], case['seed'])


def source_values(p, waves, case, indices, device):
    c, model = source_model(source_path(p, case))
    before = {k: v.clone() for k, v in model.state_dict().items()}
    x = normalized_tensor(waves[indices], np.array(c['source_mean']), np.array(c['source_scale']), device)
    model = model.to(device)
    values, prob = features(model, x), class1_probability(network_logits(model, x))
    for key, value in model.state_dict().items():
        torch.testing.assert_close(value.cpu(), before[key], rtol=0, atol=0)
    if any(v.grad is not None for v in model.parameters()):
        raise ValueError('Source gradient unexpectedly created')
    return values, prob


def prepare(output):
    p = read(PROTOCOL)
    prior = HERE / p['prior_run']
    pp, old, stats, waves, cases = load_prior(prior)
    frozen_prior(prior)
    if digest(prior / 'results.json') != p['prior_results_sha256']:
        raise ValueError('Prior result changed')
    for key in ('participants', 'channels', 'seeds'):
        if p[key] != pp[key]:
            raise ValueError('Fixed scope changed: ' + key)
    for case in cases:
        fit_validation_indices(case, stats['subjects'], stats['order'])
    output.mkdir(parents=True, exist_ok=False)
    (output / 'models').mkdir()
    (output / 'code_snapshot').mkdir()
    for name in SOURCES:
        shutil.copy2(HERE / name, output / 'code_snapshot' / name)
    save(output / 'protocol.json', p)
    save(output / 'case_manifest.json', cases)
    inputs = {str(prior / name): digest(prior / name) for name in ('results.json', 'protocol.json', 'case_manifest.json', 'lock.json', 'source_freeze.json', 'verification.json', 'integer_count_audit.json')}
    for case in cases:
        for path in (source_path(p, case), new_checkpoint(prior, case, 'SOURCE_PERSON_HEAD'),
                     prediction(prior, case, 'CROSS_ORIGINAL'), prediction(prior, case, 'SOURCE_PERSON_HEAD')):
            inputs[str(path)] = digest(path)
    save(output / 'lock.json', {'declared_at_local': datetime.now().isoformat(),
         'source_sha256': {str(HERE / name): digest(HERE / name) for name in SOURCES},
         'input_sha256': inputs, 'case_manifest_sha256': digest(output / 'case_manifest.json'),
         'frozen_package_sha256': digest(FROZEN), 'test_previously_exposed': True,
         'confirmation_eeg_read': False, 'raw_mat_read': False, 'board_accessed': False})
    print('PREPARED90 cases;360 shared ridge solves;180 selected states;29760 predictions', flush=True)


def load(output):
    lock = read(output / 'lock.json')
    for path, expected in {**lock['source_sha256'], **lock['input_sha256']}.items():
        if digest(path) != expected:
            raise ValueError('Locked source/input changed: ' + path)
    p = read(output / 'protocol.json')
    if p != read(PROTOCOL) or digest(output / 'case_manifest.json') != lock['case_manifest_sha256']:
        raise ValueError('Protocol/cases changed')
    _, old, stats, waves, cases = load_prior(HERE / p['prior_run'])
    frozen_prior(HERE / p['prior_run'])
    if cases != read(output / 'case_manifest.json'):
        raise ValueError('Prior splits changed')
    return p, old, stats, waves, cases


def train(output):
    if (output / 'source_freeze.json').exists() or (output / 'target_access.json').exists():
        raise RuntimeError('Frozen/scored run cannot be refitted')
    p, old, stats, waves, cases = load(output)
    configure_torch(old['compute'])
    started = time.monotonic()
    for case in cases:
        if any(checkpoint(output, case, m).exists() for m in NEW):
            if not all(checkpoint(output, case, m).exists() and checkpoint(output, case, m).with_suffix('.json').exists() for m in NEW):
                raise RuntimeError('Partial case preserved; diagnose before resuming')
            continue
        fitting, validation = fit_validation_indices(case, stats['subjects'], stats['order'])
        ffit, pfit = source_values(p, waves, case, fitting, 'cpu')
        fval, pval = source_values(p, waves, case, validation, 'cpu')
        with np.load(new_checkpoint(HERE / p['prior_run'], case, 'SOURCE_PERSON_HEAD'), allow_pickle=False) as head:
            np.testing.assert_array_equal(head['fit_indices'], fitting)
            np.testing.assert_array_equal(head['fit_features'], ffit)
        scaler = StandardScaler().fit(ffit)
        zfit, zval = scaler.transform(ffit), scaler.transform(fval)
        solutions = [fit_residual(zfit, stats['labels'][fitting], pfit, alpha) for alpha in p['alphas_in_tie_preference_order']]
        coef, intercept = np.stack([s[0] for s in solutions]), np.array([s[1] for s in solutions])
        for method in NEW:
            cap = p['bounded_probability_residual_cap'] if method == NEW[0] else None
            best, history = select_candidate(p, coef, intercept, zval, pval, stats['labels'][validation], cap)
            chosen = history[best]
            path = checkpoint(output, case, method)
            np.savez_compressed(path, mean=scaler.mean_, scale=scaler.scale_, coefficients=coef, intercepts=intercept,
                fit_features=ffit, fit_probability=pfit, fit_indices=fitting, validation_indices=validation,
                selected_index=best, alpha_index=-1 if chosen['alpha_index'] is None else chosen['alpha_index'],
                strength=chosen['strength'], cap=-1. if cap is None else cap)
            save(path.with_suffix('.json'), {'case': case, 'method': method, 'cap': cap, 'selected_index': best,
                'selected': chosen, 'validation_candidates': history, 'fit_indices': fitting.tolist(),
                'validation_indices': validation.tolist(), 'source_checkpoint_sha256': digest(source_path(p, case)),
                'all_source_tensors_unchanged': True, 'test_forwarded': False, 'control_enabled': False})
        print('RESIDUAL_FROZEN_CASE', case['person'], case['seed'], flush=True)
    files = sorted((output / 'models').glob('*'))
    if len(files) != 360:
        raise ValueError('Expected180 selected states and180 metadata files')
    save(output / 'source_freeze.json', {'at_local': datetime.now().isoformat(), 'selected_states': 180,
        'shared_ridge_solutions': 360, 'files': {str(path): digest(path) for path in files},
        'elapsed_pc_seconds': time.monotonic() - started, 'test_forwarded': False, 'source_weights_changed': False})


def frozen(output):
    freeze = read(output / 'source_freeze.json')
    if freeze['selected_states'] != 180 or freeze['test_forwarded'] or freeze['source_weights_changed']:
        raise ValueError('Incomplete/invalid freeze')
    for path, expected in freeze['files'].items():
        if digest(path) != expected:
            raise ValueError('Frozen model changed: ' + path)
    return freeze


def adapter_scores(state, values, base):
    index = int(state['alpha_index'])
    residual = np.zeros(len(base)) if index < 0 else ((values - state['mean']) / state['scale']) @ state['coefficients'][index] + state['intercepts'][index]
    cap = None if float(state['cap']) < 0 else float(state['cap'])
    return corrected_probability(base, residual, float(state['strength']), cap)


def evaluate(output):
    if (output / 'results.json').exists():
        raise RuntimeError('Completed result preserved')
    p, old, stats, waves, cases = load(output)
    freeze = frozen(output)
    configure_torch(old['compute'])
    if not (output / 'target_access.json').exists():
        save(output / 'target_access.json', {'at_local': datetime.now().isoformat(), 'freeze_at': freeze['at_local'], 'test_previously_exposed': True})
    for case in cases:
        indices = np.array(case['test'])
        values, base = source_values(p, waves, case, indices, 'cpu')
        for method in p['methods']:
            if prediction(output, case, method).exists():
                continue
            if method in NEW:
                with np.load(checkpoint(output, case, method), allow_pickle=False) as state:
                    scores = adapter_scores(state, values, base)
                pred = (scores > .5).astype(int)
            else:
                with np.load(prediction(HERE / p['prior_run'], case, method), allow_pickle=False) as prior:
                    np.testing.assert_array_equal(prior['indices'], indices)
                    scores, pred = prior['scores'].copy(), prior['predictions'].copy()
            save_prediction(output, case['person'], method, case['seed'], indices, stats['labels'][indices], scores, pred,
                {'case': case, 'method': method, 'personal_labels_used': method != 'CROSS_ORIGINAL', 'control_enabled': False})
        print('RESIDUAL_TEST_CASE', case['person'], case['seed'], flush=True)
    summarize(output, p, cases)


def summarize(output, p, cases):
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 30, (p['bootstrap']['draws'], 30))
    methods, hashes = {}, {}
    for method in p['methods']:
        rows = []
        for person in p['participants']:
            reps = []
            for case in [c for c in cases if c['person'] == person]:
                path = prediction(output, case, method)
                with np.load(path, allow_pickle=False) as saved:
                    ba, f1, matrix = metric(saved['labels'], saved['predictions'])
                hashes[str(path)] = digest(path)
                reps.append({'seed': case['seed'], 'ba': ba, 'macro_f1': f1, 'confusion': matrix})
            rows.append({'person': person, 'trials': len(case['test']), 'ba': float(np.mean([r['ba'] for r in reps])),
                         'macro_f1': float(np.mean([r['macro_f1'] for r in reps])), 'per_seed': reps})
        v = np.array([r['ba'] for r in rows])
        methods[method] = {'mean_person_ba': float(v.mean()), 'between_person_sd': float(v.std(ddof=1)),
            'mean_lowest8_ba': float(np.sort(v)[:8].mean()), 'mean_person_f1': float(np.mean([r['macro_f1'] for r in rows])),
            'person95ci': np.quantile(v[draws].mean(1), [.025, .975]).tolist(), 'per_person': rows}
    pairs = [[p['primary_candidate'], p['primary_reference']]] + p['secondary_comparisons']
    comparisons = {}
    for j, (candidate, reference) in enumerate(pairs):
        delta = np.array([r['ba'] for r in methods[candidate]['per_person']]) - np.array([r['ba'] for r in methods[reference]['per_person']])
        ci = np.quantile(delta[draws].mean(1), [.025, .975]).tolist()
        weak_delta = methods[candidate]['mean_lowest8_ba'] - methods[reference]['mean_lowest8_ba']
        gate = bool(j == 0 and delta.mean() >= p['development_gate']['gain_at_least'] and ci[0] > 0 and weak_delta >= -p['development_gate']['lowest8_mean_drop_at_most'])
        comparisons[candidate + '_minus_' + reference] = {'primary': j == 0, 'mean_gain': float(delta.mean()),
            'paired_ci': ci, 'coverage': .95, 'per_person_delta': delta.tolist(), 'lowest8_mean_difference': weak_delta,
            'people_improved': int((delta > 1e-12).sum()), 'people_declined': int((delta < -1e-12).sum()), 'development_gate': gate}
    diagnostics = {}
    for method in NEW:
        changed, rescued, harmed, fallbacks = 0, 0, 0, 0
        selections = []
        for case in cases:
            meta = read(checkpoint(output, case, method).with_suffix('.json'))
            selections.append({'person': case['person'], 'seed': case['seed'], **meta['selected']})
            fallbacks += meta['selected']['strength'] == 0
            with np.load(prediction(output, case, method), allow_pickle=False) as s, np.load(prediction(output, case, 'CROSS_ORIGINAL'), allow_pickle=False) as b:
                old_correct, new_correct = b['predictions'] == b['labels'], s['predictions'] == s['labels']
                changed += int(np.count_nonzero(s['predictions'] != b['predictions']))
                rescued += int(np.count_nonzero(~old_correct & new_correct))
                harmed += int(np.count_nonzero(old_correct & ~new_correct))
        diagnostics[method] = {'identity_fallback_cases': fallbacks, 'changed_predictions': changed, 'rescued_predictions': rescued,
            'harmed_predictions': harmed, 'denominator': 7440, 'selected_configs': selections}
    prior = HERE / p['prior_run']
    manifest = read(HERE / read(prior / 'protocol.json')['original_run'] / 'trial_manifest.json')
    unique = {i for c in cases for i in c['test']}
    save(output / 'results.json', {'scope': p['scope'], 'methods': methods, 'comparisons': comparisons, 'diagnostics': diagnostics,
        'scored_unique_trials': len(unique), 'scored_author_flags': sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique),
        'prediction_sha256': hashes, 'completed_at_local': datetime.now().isoformat(), 'board_accessed': False,
        'confirmation_eeg_read': False, 'deployment_authorized': False, 'control_enabled': False})
    print({m: v['mean_person_ba'] for m, v in methods.items()}, flush=True)
    print(comparisons, flush=True)


def verify(output):
    if (output / 'verification.json').exists():
        raise RuntimeError('Existing verification preserved')
    p, old, stats, waves, cases = load(output)
    frozen(output)
    configure_torch(old['compute'])
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA consistency check unavailable')
    result = read(output / 'results.json')
    rebuilt, count, coef_error, score_error = 0, 0, 0., 0.
    for case in cases:
        fit, val = fit_validation_indices(case, stats['subjects'], stats['order'])
        values, base = source_values(p, waves, case, fit, 'cpu')
        vvalues, vbase = source_values(p, waves, case, val, 'cpu')
        scaler = StandardScaler().fit(values)
        coefficients, intercepts = [], []
        for alpha in p['alphas_in_tie_preference_order']:
            with threadpool_limits(limits=1):
                alternative = Ridge(alpha=len(fit) * alpha, solver='svd').fit(scaler.transform(values), stats['labels'][fit] - base)
            coefficients.append(alternative.coef_); intercepts.append(alternative.intercept_); rebuilt += 1
        coefficients, intercepts = np.array(coefficients), np.array(intercepts)
        for method in NEW:
            with np.load(checkpoint(output, case, method), allow_pickle=False) as state:
                np.testing.assert_array_equal(state['fit_features'], values)
                np.testing.assert_array_equal(state['fit_probability'], base)
                np.testing.assert_array_equal(state['mean'], scaler.mean_)
                np.testing.assert_array_equal(state['scale'], scaler.scale_)
                for key, reference in (('coefficients', coefficients), ('intercepts', intercepts)):
                    np.testing.assert_allclose(state[key], reference, rtol=1e-9, atol=1e-9)
                    coef_error = max(coef_error, float(np.max(np.abs(state[key] - reference))))
                cap = None if method == NEW[1] else p['bounded_probability_residual_cap']
                best, history = select_candidate(p, coefficients, intercepts, scaler.transform(vvalues), vbase, stats['labels'][val], cap)
                meta = read(checkpoint(output, case, method).with_suffix('.json'))
                assert best == meta['selected_index'] == int(state['selected_index']) and history == meta['validation_candidates']
        indices = np.array(case['test'])
        gpu_features, gpu_base = source_values(p, waves, case, indices, 'cuda:0')
        for method in p['methods']:
            path = prediction(output, case, method)
            assert digest(path) == result['prediction_sha256'][str(path)]
            if method in NEW:
                with np.load(checkpoint(output, case, method), allow_pickle=False) as state:
                    scores = adapter_scores(state, gpu_features, gpu_base)
                pred = (scores > .5).astype(int)
            elif method == 'SOURCE_PERSON_HEAD':
                scores = head_scores(HERE / p['prior_run'], read(HERE / p['prior_run'] / 'protocol.json'), waves, case, indices)
                pred = (scores > 0).astype(int)
            else:
                c, model = source_model(source_path(p, case))
                scores = network_logits(model.to('cuda:0'), normalized_tensor(waves[indices], np.array(c['source_mean']), np.array(c['source_scale']), 'cuda:0'))
                pred = scores.argmax(1)
            with np.load(path, allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['predictions'], pred)
                np.testing.assert_allclose(saved['scores'], scores, rtol=2e-5, atol=2e-5)
                score_error = max(score_error, float(np.max(np.abs(saved['scores'] - scores))))
            count += len(indices)
        print('RESIDUAL_VERIFY_CASE', case['person'], case['seed'], flush=True)
    assert rebuilt == 360 and count == 29760
    assert digest(FROZEN) == read(output / 'lock.json')['frozen_package_sha256']
    save(output / 'verification.json', {'passed': True, 'ridge_solutions_svd_rebuilt': rebuilt,
        'all180_validation_selections_rebuilt': True, 'predictions_recomputed': count, 'new_residual_CPU_CUDA_classes_exact': True,
        'max_abs_coefficient_error': coef_error, 'max_abs_score_error': score_error, 'formal_package_unchanged': True,
        'results_sha256': digest(output / 'results.json'), 'at_local': datetime.now().isoformat()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'train', 'evaluate', 'verify'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    {'prepare': prepare, 'train': train, 'evaluate': evaluate, 'verify': verify}[args.action](args.output)

"""Frozen-weight, train-input-only BN mechanism check on original30."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import time

from mi_person_transfer_diagnostic import (
    load as load_prior, frozen as frozen_prior, read, save, digest, source_model,
    old_checkpoint, new_checkpoint, metric, prediction,
)
from mi_crossfield_stability import recalibrate_bn
from mi_comparison_models import configure_torch, normalized_tensor, network_logits, torch
from mi_model_comparison import save_prediction, FROZEN
import numpy as np

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / 'output/mi_bn_trainonly_20261002'
PROTOCOL = HERE / 'mi_bn_trainonly_protocol.json'
BASES = {'CROSS_SOURCE_BN': 'CROSS_ORIGINAL', 'PERSON_BN': 'PERSON_ONLY', 'MATCHED80_BN': 'CROSS_MATCHED80'}
SOURCES = ('mi_bn_trainonly.py', 'mi_bn_trainonly_protocol.json', 'MI_BN_TRAINONLY_PLAN.md',
           'test_mi_bn_trainonly.py', 'audit_mi_bn_trainonly.py', 'report_mi_bn_trainonly.py',
           'mi_crossfield_stability.py', 'mi_comparison_models.py', 'mi_person_transfer_diagnostic.py',
           'mi_model_comparison.py')


def calibration_indices(case, subjects, order, method):
    if method == 'CROSS_SOURCE_BN':
        indices = np.flatnonzero(np.isin(subjects, case['original_source_fold']['fit_people']))
        forbidden = np.flatnonzero(np.isin(subjects, case['original_source_fold']['validation_people']) | (subjects == case['person']))
    elif method == 'PERSON_BN':
        indices = np.asarray(case['personal_fit'], dtype=int)
        expected = np.flatnonzero((subjects == case['person']) & (order < 80))
        np.testing.assert_array_equal(indices, expected)
        forbidden = np.flatnonzero((subjects != case['person']) | (order >= 80))
    elif method == 'MATCHED80_BN':
        indices = np.asarray(case['matched_fit'], dtype=int)
        if len(indices) != 80 or not np.isin(subjects[indices], case['original_source_fold']['fit_people']).all():
            raise ValueError('Only the exact old80 fitting budget allowed')
        forbidden = np.asarray(case['matched_validation'] + case['test'], dtype=int)
    else:
        raise ValueError('Unknown BN condition')
    if not len(indices) or len(set(indices)) != len(indices) or not np.all(np.diff(indices) > 0):
        raise ValueError('Distinct ascending nonempty fitting indices required')
    if np.intersect1d(indices, forbidden).size:
        raise ValueError('Validation/test data cannot calibrate BN')
    return indices


def original_path(p, case, method):
    prior = HERE / p['prior_run']
    base = BASES.get(method, method)
    if base == 'CROSS_ORIGINAL':
        original = HERE / read(prior / 'protocol.json')['original_run']
        return old_checkpoint(original, case['person'], case['seed'])
    return new_checkpoint(prior, case, base)


def calibrated_path(output, case, method):
    return output / 'models' / f's{case["person"]:02d}_{method}_seed{case["seed"]}.pt'


def compare_non_bn(before, after):
    if before.keys() != after.keys():
        raise ValueError('Checkpoint tensor keys changed')
    changed = []
    for key in before:
        if not torch.equal(before[key].cpu(), after[key].cpu()):
            if not key.endswith(('.running_mean', '.running_var', '.num_batches_tracked')):
                raise ValueError('Learned/non-BN tensor changed: ' + key)
            changed.append(key)
    if not changed:
        raise ValueError('No BN buffer changed; calibration did not execute')
    return changed


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
        for method in BASES:
            calibration_indices(case, stats['subjects'], stats['order'], method)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'models').mkdir()
    (output / 'code_snapshot').mkdir()
    for name in SOURCES:
        shutil.copy2(HERE / name, output / 'code_snapshot' / name)
    save(output / 'protocol.json', p)
    save(output / 'case_manifest.json', cases)
    inputs = {str(prior / name): digest(prior / name) for name in ('results.json', 'protocol.json', 'case_manifest.json', 'lock.json', 'source_freeze.json', 'verification.json', 'integer_count_audit.json')}
    for case in cases:
        for base in BASES.values():
            path = original_path(p, case, base)
            inputs[str(path)] = digest(path)
            path = prediction(prior, case, base)
            inputs[str(path)] = digest(path)
    save(output / 'lock.json', {
        'declared_at_local': datetime.now().isoformat(),
        'source_sha256': {str(HERE / name): digest(HERE / name) for name in SOURCES},
        'input_sha256': inputs, 'case_manifest_sha256': digest(output / 'case_manifest.json'),
        'frozen_package_sha256': digest(FROZEN), 'test_previously_exposed': True,
        'confirmation_eeg_read': False, 'board_accessed': False,
    })
    print('PREPARED270 train-only BN states; no gradient training; six conditions44640 predictions', flush=True)


def load(output):
    lock = read(output / 'lock.json')
    for path, expected in {**lock['source_sha256'], **lock['input_sha256']}.items():
        if digest(path) != expected:
            raise ValueError('Frozen input/code changed: ' + path)
    p = read(output / 'protocol.json')
    if p != read(PROTOCOL) or digest(output / 'case_manifest.json') != lock['case_manifest_sha256']:
        raise ValueError('Protocol/cases changed')
    _, old, stats, waves, cases = load_prior(HERE / p['prior_run'])
    frozen_prior(HERE / p['prior_run'])
    if cases != read(output / 'case_manifest.json'):
        raise ValueError('Prior splits changed')
    return p, old, stats, waves, cases


def calibrate(output):
    if (output / 'source_freeze.json').exists() or (output / 'target_access.json').exists():
        raise RuntimeError('Frozen/scored states cannot be recalibrated')
    p, old, stats, waves, cases = load(output)
    configure_torch(old['compute'])
    if not torch.cuda.is_available():
        raise RuntimeError('Declared CUDA unavailable')
    device = p['recalibration']['device']
    started = time.monotonic()
    for case in cases:
        for method in BASES:
            path = calibrated_path(output, case, method)
            if path.exists():
                if not path.with_suffix('.json').exists():
                    raise RuntimeError('Partial state must be diagnosed, not overwritten')
                continue
            origin = original_path(p, case, method)
            c, model = source_model(origin)
            before = {key: value.clone() for key, value in model.state_dict().items()}
            indices = calibration_indices(case, stats['subjects'], stats['order'], method)
            x = normalized_tensor(waves[indices], np.array(c['source_mean']), np.array(c['source_scale']), device)
            model = model.to(device)
            rng = torch.cuda.get_rng_state().clone()
            recalibrate_bn(model, x, p['recalibration']['batch_size'])
            torch.testing.assert_close(rng, torch.cuda.get_rng_state(), rtol=0, atol=0)
            if any(parameter.grad is not None for parameter in model.parameters()):
                raise ValueError('Unexpected parameter gradient')
            state = {key: value.detach().cpu() for key, value in model.state_dict().items()}
            changed = compare_non_bn(before, state)
            metadata = {'method': method, 'person': case['person'], 'seed': case['seed'],
                        'fit_indices': indices.tolist(), 'source_checkpoint_sha256': digest(origin),
                        'only_BN_buffers_changed': changed, 'learned_tensors_exact': True,
                        'dropout_disabled': all(not layer.training for layer in model.modules()),
                        'labels_used': False, 'new_test_forward': False}
            c.update(state_dict=state, BN_diagnostic=metadata)
            torch.save(c, path)
            save(path.with_suffix('.json'), metadata)
        print('BN_FROZEN_CASE', case['person'], case['seed'], 'elapsed', round(time.monotonic() - started, 1), flush=True)
    files = sorted((output / 'models').glob('*'))
    if len(files) != 540:
        raise ValueError('Expected270 states and270 metadata files')
    save(output / 'source_freeze.json', {'at_local': datetime.now().isoformat(), 'calibrated_objects': 270,
        'files': {str(path): digest(path) for path in files}, 'elapsed_pc_seconds': time.monotonic() - started,
        'new_test_forwarded': False, 'learned_weights_changed': False})


def check_frozen(output):
    freeze = read(output / 'source_freeze.json')
    if freeze['calibrated_objects'] != 270 or freeze['new_test_forwarded'] or freeze['learned_weights_changed']:
        raise ValueError('Incomplete or invalid BN freeze')
    for path, expected in freeze['files'].items():
        if digest(path) != expected:
            raise ValueError('Calibrated checkpoint changed: ' + path)
    return freeze


def summarize(output, p, stats, cases):
    hashes, methods = {}, {}
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 30, (10000, 30))
    for method in p['methods']:
        rows = []
        for person in p['participants']:
            repetitions = []
            for case in [c for c in cases if c['person'] == person]:
                path = prediction(output, case, method)
                with np.load(path, allow_pickle=False) as saved:
                    np.testing.assert_array_equal(saved['indices'], case['test'])
                    np.testing.assert_array_equal(saved['labels'], stats['labels'][saved['indices']])
                    ba, f1, matrix = metric(saved['labels'], saved['predictions'])
                hashes[str(path)] = digest(path)
                repetitions.append({'seed': case['seed'], 'ba': ba, 'macro_f1': f1, 'confusion': matrix})
            rows.append({'person': person, 'trials': len(case['test']), 'ba': float(np.mean([r['ba'] for r in repetitions])),
                         'macro_f1': float(np.mean([r['macro_f1'] for r in repetitions])), 'per_seed': repetitions})
        values = np.array([r['ba'] for r in rows])
        methods[method] = {'mean_person_ba': float(values.mean()), 'between_person_sd': float(values.std(ddof=1)),
            'mean_lowest8_ba': float(np.sort(values)[:8].mean()), 'mean_person_f1': float(np.mean([r['macro_f1'] for r in rows])),
            'person95ci': np.quantile(values[draws].mean(1), [.025, .975]).tolist(), 'per_person': rows}
    comparisons = {}
    for primary, pairs in ((True, p['primary_comparisons']), (False, p['secondary_comparisons'])):
        for pair in pairs:
            candidate, reference = pair['candidate'], pair['reference']
            delta = np.array([r['ba'] for r in methods[candidate]['per_person']]) - np.array([r['ba'] for r in methods[reference]['per_person']])
            coverage = p['bootstrap']['primary_interval' if primary else 'secondary_interval']
            tail = (1 - coverage) / 2
            ci = np.quantile(delta[draws].mean(1), [tail, 1 - tail]).tolist()
            threshold = pair.get('gain_at_least')
            comparisons[candidate + '_minus_' + reference] = {'primary': primary, 'coverage': coverage,
                'mean_gain': float(delta.mean()), 'paired_ci': ci, 'per_person_delta': delta.tolist(),
                'people_improved': int((delta > 1e-12).sum()), 'people_declined': int((delta < -1e-12).sum()),
                'gain_threshold': threshold, 'development_gate': bool(primary and delta.mean() >= threshold and ci[0] > 0)}
    prior = HERE / p['prior_run']
    manifest = read(HERE / read(prior / 'protocol.json')['original_run'] / 'trial_manifest.json')
    unique = {i for case in cases for i in case['test']}
    result = {'scope': p['scope'], 'methods': methods, 'comparisons': comparisons,
        'scored_unique_trials': len(unique), 'scored_author_flags': sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique),
        'prediction_sha256': hashes, 'completed_at_local': datetime.now().isoformat(),
        'new_learned_weights': False, 'confirmation_eeg_read': False, 'board_accessed': False,
        'deployment_authorized': False, 'control_enabled': False}
    save(output / 'results.json', result)
    print({m: v['mean_person_ba'] for m, v in methods.items()}, flush=True)
    print(result['comparisons'], flush=True)


def evaluate(output):
    if (output / 'results.json').exists():
        raise RuntimeError('Completed result preserved')
    p, old, stats, waves, cases = load(output)
    freeze = check_frozen(output)
    configure_torch(old['compute'])
    if not (output / 'target_access.json').exists():
        save(output / 'target_access.json', {'at_local': datetime.now().isoformat(), 'freeze_at': freeze['at_local'], 'previous_target_exposure_declared': True})
    for case in cases:
        indices = np.array(case['test'])
        for method in p['methods']:
            if prediction(output, case, method).exists():
                continue
            if method in BASES:
                c, model = source_model(calibrated_path(output, case, method))
                device = p['recalibration']['device']
                x = normalized_tensor(waves[indices], np.array(c['source_mean']), np.array(c['source_scale']), device)
                scores = network_logits(model.to(device), x)
            else:
                with np.load(prediction(HERE / p['prior_run'], case, method), allow_pickle=False) as saved:
                    np.testing.assert_array_equal(saved['indices'], indices)
                    scores = saved['scores'].copy()
            save_prediction(output, case['person'], method, case['seed'], indices, stats['labels'][indices], scores, scores.argmax(1),
                            {'case': case, 'method': method, 'no_weight_training': True, 'control_enabled': False})
        print('BN_TEST_CASE', case['person'], case['seed'], flush=True)
    summarize(output, p, stats, cases)


def verify(output):
    target = output / 'verification.json'
    if target.exists():
        raise RuntimeError('Existing numerical verification preserved')
    p, old, stats, waves, cases = load(output)
    check_frozen(output)
    configure_torch(old['compute'])
    result = read(output / 'results.json')
    count, rebuilt, max_error, max_buffer_error = 0, 0, 0., 0.
    for case in cases:
        indices = np.array(case['test'])
        for method in p['methods']:
            path = calibrated_path(output, case, method) if method in BASES else original_path(p, case, method)
            c, model = source_model(path)
            if method in BASES:
                origin, reference = source_model(original_path(p, case, method))
                compare_non_bn(origin['state_dict'], c['state_dict'])
                assert origin['source_mean'] == c['source_mean'] and origin['source_scale'] == c['source_scale']
                fitting = calibration_indices(case, stats['subjects'], stats['order'], method)
                np.testing.assert_array_equal(c['BN_diagnostic']['fit_indices'], fitting)
                xfit = normalized_tensor(waves[fitting], np.array(origin['source_mean']), np.array(origin['source_scale']), 'cpu')
                recalibrate_bn(reference, xfit, p['recalibration']['batch_size'])
                for key, value in reference.state_dict().items():
                    if key.endswith(('.running_mean', '.running_var')):
                        torch.testing.assert_close(value, c['state_dict'][key], rtol=2e-5, atol=2e-6)
                        max_buffer_error = max(max_buffer_error, float((value - c['state_dict'][key]).abs().max()))
                    else:
                        torch.testing.assert_close(value, c['state_dict'][key], rtol=0, atol=0)
                rebuilt += 1
            scores = network_logits(model, normalized_tensor(waves[indices], np.array(c['source_mean']), np.array(c['source_scale']), 'cpu'))
            predpath = prediction(output, case, method)
            assert digest(predpath) == result['prediction_sha256'][str(predpath)]
            with np.load(predpath, allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['indices'], indices)
                np.testing.assert_array_equal(saved['labels'], stats['labels'][indices])
                np.testing.assert_array_equal(saved['predictions'], scores.argmax(1))
                np.testing.assert_allclose(saved['scores'], scores, rtol=2e-5, atol=2e-5)
                max_error = max(max_error, float(np.max(np.abs(saved['scores'] - scores))))
            count += len(indices)
        print('BN_VERIFY_CASE', case['person'], case['seed'], flush=True)
    assert count == 44640 and rebuilt == 270
    assert digest(FROZEN) == read(output / 'lock.json')['frozen_package_sha256']
    save(target, {'passed': True, 'BN_states_cpu_rebuilt': rebuilt, 'learned_tensors_and_scalers_exact': True,
                  'predictions_cpu_recomputed': count, 'classes_exact': True, 'max_abs_score_error': max_error,
                  'max_abs_BN_buffer_error': max_buffer_error, 'formal_package_unchanged': True,
                  'results_sha256': digest(output / 'results.json'), 'at_local': datetime.now().isoformat()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'calibrate', 'evaluate', 'verify'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    {'prepare': prepare, 'calibrate': calibrate, 'evaluate': evaluate, 'verify': verify}[args.action](args.output)

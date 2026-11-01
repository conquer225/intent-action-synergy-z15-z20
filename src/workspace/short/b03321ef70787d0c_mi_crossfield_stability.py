"""Train-only bounded person risk and local weight averaging; never deploy."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import time

from mi_comparison_models import (EEGNetSmall, configure_torch, channel_scaler,
                                 normalized_tensor, network_logits, mean_person_ba, torch)
import numpy as np
from sklearn.metrics import confusion_matrix, f1_score

from cho2017_training_diagnostic import save
from mi_model_comparison import HERE, FROZEN, load_run, fold_indices, save_prediction

PROTOCOL = HERE / 'mi_crossfield_protocol.json'
OUTPUT = HERE / 'output/mi_crossfield_stability_20261001'
NEW_SOURCES = ['mi_crossfield_stability.py', 'mi_crossfield_protocol.json',
               'MI_CROSSFIELD_PLAN.md', 'test_mi_crossfield_stability.py']
OBJECTIVE_METHODS = {'PERSON_EQUAL': ('EQUAL_BEST', 'EQUAL_AVERAGE'),
                     'BOUNDED_RISK': ('RISK_BEST', 'RISK_AVERAGE')}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def bounded_risk_weights(risks, settings):
    risks = np.asarray(risks, dtype=np.float64)
    if risks.ndim != 1 or len(risks) < 2 or not np.isfinite(risks).all():
        raise ValueError('At least2 finite group risks required')
    size = len(risks)
    lower, upper = settings['relative_weight_min']/size, settings['relative_weight_max']/size
    temperature = settings['temperature']
    if not (0 < lower < 1/size < upper and temperature > 0):
        raise ValueError('Invalid risk budget')
    logits = np.maximum((risks-risks.max())/temperature, -60.)
    left, right = -100., 100.
    for _ in range(100):
        center = (left+right)/2
        if np.clip(np.exp(center+logits), lower, upper).sum() > 1:
            right = center
        else:
            left = center
    weights = np.clip(np.exp((left+right)/2+logits), lower, upper)
    np.testing.assert_allclose(weights.sum(), 1., rtol=0, atol=1e-12)
    return weights


def sample_weights(people, group_weights):
    groups, inverse, counts = np.unique(people, return_inverse=True, return_counts=True)
    if len(groups) != len(group_weights) or not np.isfinite(group_weights).all():
        raise ValueError('Group budget and source people disagree')
    return len(people)*np.asarray(group_weights)[inverse]/counts[inverse], groups, inverse, counts


def state_copy(model):
    return {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}


def average_states(states, center_state):
    if not states or any(set(state) != set(center_state) for state in states):
        raise ValueError('Compatible nonempty state neighborhood required')
    result = {}
    for key, reference in center_state.items():
        if reference.is_floating_point():
            result[key] = torch.stack([state[key].to(torch.float64) for state in states]).mean(0).to(reference.dtype)
        else:
            result[key] = reference.clone()
    return result


@torch.no_grad()
def recalibrate_bn(model, fit_x, batch_size=256):
    """Only source-fit input; eval dropout, train BN with cumulative batch moments."""
    model.eval()
    batch_norms = [layer for layer in model.modules() if isinstance(layer, torch.nn.BatchNorm2d)]
    momenta = [layer.momentum for layer in batch_norms]
    for layer in batch_norms:
        layer.reset_running_stats()
        layer.momentum = None
        layer.train()
    for start in range(0, len(fit_x), batch_size):
        model(fit_x[start:start+batch_size])
    for layer, momentum in zip(batch_norms, momenta):
        layer.momentum = momentum
    model.eval()


def train_source(fit_x, fit_y, fit_people, val_x, val_y, val_people,
                 config, risk_settings, average_settings, objective, seed):
    """No target data API. Same batches/initialization across both objectives."""
    if objective not in OBJECTIVE_METHODS or set(fit_people) & set(val_people):
        raise ValueError('Unknown objective or overlapping source people')
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = fit_x.device
    model = EEGNetSmall(config).to(device)
    labels = torch.as_tensor(fit_y, dtype=torch.long, device=device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'],
                                 betas=tuple(config['betas']), weight_decay=config['weight_decay'])
    groups, inverse, counts = np.unique(fit_people, return_inverse=True, return_counts=True)
    q = np.full(len(groups), 1/len(groups))
    ema = None
    best_ba, best_epoch = -1., 0
    history, states = [], []
    started = time.monotonic()
    for epoch in range(1, config['epochs_max']+1):
        model.train()
        weights, _, _, _ = sample_weights(fit_people, q)
        weights = torch.as_tensor(weights, dtype=torch.float32, device=device)
        order = torch.randperm(len(fit_x), device=device)
        losses_by_trial = np.empty(len(fit_x), dtype=np.float64)
        for offset in range(0, len(order), config['batch_size']):
            selected = order[offset:offset+config['batch_size']]
            optimizer.zero_grad(set_to_none=True)
            losses = torch.nn.functional.cross_entropy(model(fit_x[selected]), labels[selected], reduction='none')
            loss = (losses*weights[selected]).mean()
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite risk loss; no fallback')
            losses_by_trial[selected.cpu().numpy()] = losses.detach().cpu().numpy()
            loss.backward()
            optimizer.step()
            model.constrain()
        group_ce = np.bincount(inverse, weights=losses_by_trial, minlength=len(groups))/counts
        alpha = risk_settings['ema_new_fraction']
        ema = group_ce.copy() if ema is None else (1-alpha)*ema+alpha*group_ce
        val_logits = network_logits(model, val_x)
        ba = mean_person_ba(val_y, val_logits.argmax(1), val_people)
        history.append({'epoch': epoch, 'source_validation_mean_person_ba': ba,
                        'source_online_group_ce': group_ce.tolist(), 'source_ema_ce': ema.tolist(),
                        'group_weights_used': q.tolist()})
        states.append(state_copy(model))
        if ba > best_ba:
            best_ba, best_epoch = ba, epoch
        if objective == 'BOUNDED_RISK' and epoch >= risk_settings['warmup_epochs']:
            q = bounded_risk_weights(ema, risk_settings)
        if epoch-best_epoch >= config['early_stop_patience']:
            break
    center = states[best_epoch-1]
    radius = average_settings['radius_epochs']
    epochs = list(range(max(1, best_epoch-radius), min(epoch, best_epoch+radius)+1))
    neighborhood = [states[index-1] for index in epochs]
    average_model = EEGNetSmall(config).to(device)
    average_model.load_state_dict(average_states(neighborhood, center))
    recalibrate_bn(average_model, fit_x)
    best_model = EEGNetSmall(config).to(device)
    best_model.load_state_dict(center)
    average_val_ba = mean_person_ba(val_y, network_logits(average_model, val_x).argmax(1), val_people)
    history_info = {'objective': objective, 'seed': seed, 'source_groups': groups.tolist(),
                    'best_epoch': best_epoch, 'completed_epochs': epoch, 'averaged_epochs': epochs,
                    'best_source_validation_ba': best_ba, 'averaged_source_validation_ba': average_val_ba,
                    'average_source_validation_used_to_select': False, 'history': history,
                    'pc_train_and_average_seconds': time.monotonic()-started, 'parameter_count': 2226}
    return state_copy(best_model), state_copy(average_model), neighborhood, history_info


def prepare(output):
    protocol = read(PROTOCOL)
    original_path = HERE/protocol['original_run']
    old, stats, waves, folds = load_run(original_path)
    if (protocol['participants'] != old['participants'] or protocol['channels'] != old['channels']
            or protocol['seeds'] != old['eegnet']['seeds']
            or digest(original_path/'results.json') != protocol['original_results_sha256']):
        raise ValueError('Original scope/configuration/evidence mismatch')
    if len(waves) != 6080 or int((stats['order'] >= 60).sum()) != 4280:
        raise ValueError('Incomplete original30 cache')
    output.mkdir(exist_ok=False, parents=True)
    snapshot = output/'code_snapshot'
    snapshot.mkdir()
    source_hashes = {str(HERE/name): digest(HERE/name) for name in NEW_SOURCES}
    for name in NEW_SOURCES:
        shutil.copy2(HERE/name, snapshot/name)
    save(output/'protocol.json', protocol)
    save(output/'network_config.json', old['eegnet'])
    save(output/'compute.json', old['compute'])
    save(output/'fold_manifest.json', folds)
    shutil.copy2(original_path/'trial_manifest.json', output/'trial_manifest.json')
    inputs = [original_path/name for name in ('waveforms.npy', 'statistics.npz', 'fold_manifest.json',
                                            'trial_manifest.json', 'results.json', 'audit.json')]
    baseline = list((original_path/'fold_predictions').glob('s*_C2_EEGNet_SMALL_seed*.npz'))
    inputs.extend(baseline)
    inputs.extend((original_path/'network_checkpoints').glob('*.pt'))
    inputs.extend((original_path/'network_checkpoints').glob('*.json'))
    if len(baseline) != 90:
        raise ValueError('All90 baseline predictions required')
    save(output/'lock.json', {'created_at_local': datetime.now().isoformat(), 'source_sha256': source_hashes,
                             'input_sha256': {str(path): digest(path) for path in inputs},
                             'frozen_package_sha256': digest(FROZEN),
                             'original_mat_opened': False, 'confirmation_eeg_read': False,
                             'former_development_eeg_read': False})
    print('PREPARED source30 only;180fits; no target forward before source freeze', flush=True)


def load(output):
    lock = read(output/'lock.json')
    for path, expected in {**lock['source_sha256'], **lock['input_sha256']}.items():
        if digest(path) != expected:
            raise ValueError('Frozen source/input changed: '+path)
    for name, original in [('protocol.json', PROTOCOL)]:
        if read(output/name) != read(original):
            raise ValueError('Output protocol altered')
    p = read(output/'protocol.json')
    old, stats, waves, folds = load_run(HERE/p['original_run'])
    if read(output/'network_config.json') != old['eegnet'] or read(output/'fold_manifest.json') != folds:
        raise ValueError('Source config/folds changed')
    return p, old, stats, waves, folds


def checkpoint_path(output, person, objective, seed):
    return output/'source_checkpoints'/f's{person:02d}_{objective}_seed{seed}.pt'


def train(output):
    if (output/'target_access.json').exists():
        raise RuntimeError('No refitting after new target scoring')
    p, old, stats, waves, folds = load(output)
    configure_torch(old['compute'])
    if not torch.cuda.is_available():
        raise RuntimeError('Locked CUDA unavailable')
    device = torch.device(old['compute']['device'])
    folder = output/'source_checkpoints'
    folder.mkdir(exist_ok=True)
    started = time.monotonic()
    completed = 0
    for fold in folds:
        fitting, validation, _ = fold_indices(stats['subjects'], stats['order'], fold)
        mean, scale = channel_scaler(waves[fitting])
        fit_x = normalized_tensor(waves[fitting], mean, scale, device)
        val_x = normalized_tensor(waves[validation], mean, scale, device)
        for objective in p['objectives']:
            for seed in p['seeds']:
                path = checkpoint_path(output, fold['target'], objective, seed)
                if path.exists():
                    history = read(path.with_suffix('.json'))
                    stored = torch.load(path, map_location='cpu', weights_only=True)
                    if stored['metadata'] != {**fold, 'objective': objective, 'seed': seed}:
                        raise ValueError('Partial/stale checkpoint')
                else:
                    best, average, neighborhood, history = train_source(
                        fit_x, stats['labels'][fitting], stats['subjects'][fitting], val_x,
                        stats['labels'][validation], stats['subjects'][validation], old['eegnet'],
                        p['risk'], p['average'], objective, seed)
                    torch.save({'best': best, 'average': average, 'neighborhood': neighborhood,
                                'config': old['eegnet'], 'source_mean': mean.tolist(), 'source_scale': scale.tolist(),
                                'metadata': {**fold, 'objective': objective, 'seed': seed}}, path)
                    save(path.with_suffix('.json'), history)
                completed += 1
                print('SOURCE_COMPLETE', completed, '/180', path.stem, 'best', history['best_epoch'],
                      'epochs', history['completed_epochs'], 'elapsed', round(time.monotonic()-started, 1), flush=True)
        del fit_x, val_x
    artifacts = list(folder.glob('*.pt'))+list(folder.glob('*.json'))
    if len(artifacts) != 360:
        raise ValueError('All180 models and histories required')
    freeze = output/'source_training_complete.json'
    if not freeze.exists():
        save(freeze, {'frozen_at_local': datetime.now().isoformat(), 'fits': 180,
                      'artifact_sha256': {str(path): digest(path) for path in artifacts},
                      'new_target_forward_count': 0, 'pc_resume_elapsed_seconds': time.monotonic()-started})


def frozen_models(output):
    freeze = read(output/'source_training_complete.json')
    if freeze['fits'] != 180 or len(freeze['artifact_sha256']) != 360:
        raise ValueError('Source freeze incomplete')
    for path, expected in freeze['artifact_sha256'].items():
        if digest(path) != expected:
            raise ValueError('Source checkpoint changed: '+path)
    return freeze


def evaluate(output):
    if (output/'results.json').exists():
        raise RuntimeError('Scores already frozen; no replacement')
    p, old, stats, waves, folds = load(output)
    freeze = frozen_models(output)
    configure_torch(old['compute'])
    device = torch.device(old['compute']['device'])
    access = output/'target_access.json'
    if not access.exists():
        save(access, {'at_local': datetime.now().isoformat(), 'source_freeze_at': freeze['frozen_at_local'],
                      'scope': 'Original30 exploratory LOSO only;former10/confirmation12 not loaded'})
    for fold in folds:
        _, _, target = fold_indices(stats['subjects'], stats['order'], fold)
        for objective in p['objectives']:
            for seed in p['seeds']:
                path = checkpoint_path(output, fold['target'], objective, seed)
                checkpoint = torch.load(path, map_location='cpu', weights_only=True)
                x = normalized_tensor(waves[target], np.array(checkpoint['source_mean']), np.array(checkpoint['source_scale']), device)
                for state_name, method in zip(('best', 'average'), OBJECTIVE_METHODS[objective]):
                    pred_path = output/'fold_predictions'/f's{fold["target"]:02d}_{method}_seed{seed}.npz'
                    if pred_path.exists():
                        continue
                    model = EEGNetSmall(checkpoint['config']).to(device)
                    model.load_state_dict(checkpoint[state_name])
                    logits = network_logits(model, x)
                    save_prediction(output, fold['target'], method, seed, target, stats['labels'][target], logits,
                                    logits.argmax(1), {**fold, 'seed': seed, 'checkpoint': str(path),
                                                      'state': state_name, 'source_selected': True, 'control_enabled': False})
        print('TARGET_FORWARDED', fold['target'], flush=True)
    summarize(output, p, stats, folds)


def prediction_path(output, protocol, person, method, seed):
    if method == 'B0_ORIGINAL_EEGNET':
        return HERE/protocol['original_run']/'fold_predictions'/f's{person:02d}_C2_EEGNet_SMALL_seed{seed}.npz'
    return output/'fold_predictions'/f's{person:02d}_{method}_seed{seed}.npz'


def integer_metrics(y, prediction):
    matrix = confusion_matrix(y, prediction, labels=[0, 1])
    recalls = np.diag(matrix)/matrix.sum(1)
    f1 = [2*matrix[i, i]/(2*matrix[i, i]+matrix[i, 1-i]+matrix[1-i, i]) for i in (0, 1)]
    return float(recalls.mean()), float(np.mean(f1)), matrix.tolist()


def summarize(output, p, stats, folds):
    methods, files = {}, {}
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 30, size=(p['bootstrap']['draws'], 30))
    for method in p['methods']:
        rows = []
        for fold in folds:
            _, _, target = fold_indices(stats['subjects'], stats['order'], fold)
            repetitions = []
            for seed in p['seeds']:
                path = prediction_path(output, p, fold['target'], method, seed)
                with np.load(path, allow_pickle=False) as pred:
                    np.testing.assert_array_equal(pred['indices'], target)
                    np.testing.assert_array_equal(pred['labels'], stats['labels'][target])
                    np.testing.assert_array_equal(pred['predictions'], pred['scores'].argmax(1))
                    ba, f1, matrix = integer_metrics(pred['labels'], pred['predictions'])
                    repetitions.append({'seed': seed, 'ba': ba, 'macro_f1': f1, 'confusion': matrix})
                files[str(path)] = digest(path)
            rows.append({'person': fold['target'], 'trials': len(target),
                         'ba': float(np.mean([r['ba'] for r in repetitions])),
                         'macro_f1': float(np.mean([r['macro_f1'] for r in repetitions])),
                         'seed_sd': float(np.std([r['ba'] for r in repetitions], ddof=1)), 'per_seed': repetitions})
        values = np.array([row['ba'] for row in rows])
        methods[method] = {'mean_person_ba': float(values.mean()), 'between_person_sd': float(values.std(ddof=1)),
                           'mean_lowest8_ba': float(np.sort(values)[:8].mean()),
                           'people_below_55': int((values < .55).sum()),
                           'mean_seed_sd': float(np.mean([r['seed_sd'] for r in rows])),
                           'mean_person_macro_f1': float(np.mean([r['macro_f1'] for r in rows])),
                           'person_bootstrap_95_ci': np.quantile(values[draws].mean(1), [.025, .975]).tolist(),
                           'per_person': rows}
    reference = methods[p['primary_reference']]
    base = np.array([row['ba'] for row in reference['per_person']])
    comparisons = {}
    tail = (1-p['bootstrap']['paired_interval'])/2
    for method in p['methods'][1:]:
        values = np.array([row['ba'] for row in methods[method]['per_person']])
        delta = values-base
        ci = np.quantile(delta[draws].mean(1), [tail, 1-tail]).tolist()
        bottom_gain = methods[method]['mean_lowest8_ba']-reference['mean_lowest8_ba']
        sd_change = methods[method]['between_person_sd']-reference['between_person_sd']
        eligible = method in p['primary_candidates']
        gate = p['gate']
        passing = (eligible and delta.mean() >= gate['mean_ba_gain_min']
                   and ci[0] > gate['adjusted_paired_ci_lower_greater_than']
                   and bottom_gain >= gate['lowest8_mean_gain_min']
                   and sd_change <= gate['between_person_sd_increase_max'])
        comparisons[method] = {'mean_ba_gain': float(delta.mean()), 'adjusted_97_5_paired_ci': ci,
                               'mean_lowest8_gain': float(bottom_gain), 'between_person_sd_change': float(sd_change),
                               'people_improved': int((delta > 1e-12).sum()), 'people_declined': int((delta < -1e-12).sum()),
                               'people_tied': int((np.abs(delta) <= 1e-12).sum()), 'predeclared_candidate': eligible,
                               'stability_gate_passed': bool(passing), 'per_person_gain': delta.tolist()}
    manifest = read(output/'trial_manifest.json')
    histories = [read(path) for path in (output/'source_checkpoints').glob('*.json')]
    report = {'scope': 'Original30 repeatedly used exploratory development;not new independent confirmation or Cyton accuracy',
              'methods': methods, 'paired_vs_original_eegnet': comparisons,
              'passing': [name for name in p['primary_candidates'] if comparisons[name]['stability_gate_passed']],
              'source_fits': len(histories), 'source_epochs': sum(h['completed_epochs'] for h in histories),
              'pc_training_total_seconds': sum(h['pc_train_and_average_seconds'] for h in histories),
              'all_trials': len(manifest), 'author_flagged_retained': sum(r['voltage_bad'] or r['emg_bad'] for r in manifest),
              'scored_trials': int((stats['order'] >= 60).sum()),
              'scored_author_flags': sum((r['voltage_bad'] or r['emg_bad']) and r['original_order'] >= 60 for r in manifest),
              'prediction_sha256': files, 'protocol_sha256': digest(PROTOCOL),
              'confirmation_eeg_read': False, 'former_development_eeg_read': False, 'board_accessed': False,
              'deployment_authorized_by_this_experiment': False, 'control_enabled': False,
              'completed_at_local': datetime.now().isoformat()}
    save(output/'results.json', report)
    print(json.dumps({'means': {m: r['mean_person_ba'] for m, r in methods.items()}, 'passing': report['passing']}, indent=2), flush=True)


def verify(output):
    p, old, stats, waves, folds = load(output)
    frozen_models(output)
    report = read(output/'results.json')
    configure_torch(old['compute'])
    errors, checked, checkpoint_checks = [], 0, 0
    for fold in folds:
        fitting, validation, target = fold_indices(stats['subjects'], stats['order'], fold)
        mean, scale = channel_scaler(waves[fitting])
        fit_x = normalized_tensor(waves[fitting], mean, scale, 'cpu')
        val_x = normalized_tensor(waves[validation], mean, scale, 'cpu')
        target_x = normalized_tensor(waves[target], mean, scale, 'cpu')
        for objective in p['objectives']:
            for seed in p['seeds']:
                path = checkpoint_path(output, fold['target'], objective, seed)
                c = torch.load(path, map_location='cpu', weights_only=True)
                h = read(path.with_suffix('.json'))
                np.testing.assert_array_equal(c['source_mean'], mean)
                np.testing.assert_array_equal(c['source_scale'], scale)
                best_index = int(np.argmax([r['source_validation_mean_person_ba'] for r in h['history']]))
                if best_index+1 != h['best_epoch']:
                    raise ValueError('Not earliest source-selected center')
                radius = p['average']['radius_epochs']
                expected_epochs = list(range(max(1, h['best_epoch']-radius), min(h['completed_epochs'], h['best_epoch']+radius)+1))
                if h['averaged_epochs'] != expected_epochs:
                    raise ValueError('Averaging neighborhood altered')
                center = c['neighborhood'][h['averaged_epochs'].index(h['best_epoch'])]
                for key in center:
                    torch.testing.assert_close(c['best'][key], center[key], rtol=0, atol=0)
                averaged = EEGNetSmall(c['config'])
                averaged.load_state_dict(average_states(c['neighborhood'], center))
                recalibrate_bn(averaged, fit_x)
                for key, value in averaged.state_dict().items():
                    torch.testing.assert_close(value, c['average'][key], rtol=0, atol=2e-5)
                weights = np.full(26, 1/26)
                ema = None
                for row in h['history']:
                    np.testing.assert_allclose(row['group_weights_used'], weights, rtol=0, atol=1e-12)
                    group_ce = np.array(row['source_online_group_ce'])
                    alpha = p['risk']['ema_new_fraction']
                    ema = group_ce if ema is None else (1-alpha)*ema+alpha*group_ce
                    np.testing.assert_allclose(row['source_ema_ce'], ema, rtol=0, atol=1e-12)
                    if objective == 'BOUNDED_RISK' and row['epoch'] >= p['risk']['warmup_epochs']:
                        weights = bounded_risk_weights(ema, p['risk'])
                for state_name, method in zip(('best', 'average'), OBJECTIVE_METHODS[objective]):
                    model = EEGNetSmall(c['config'])
                    model.load_state_dict(c[state_name])
                    cpu_logits = network_logits(model, target_x)
                    pred_path = prediction_path(output, p, fold['target'], method, seed)
                    if digest(pred_path) != report['prediction_sha256'][str(pred_path)]:
                        raise ValueError('Prediction changed')
                    with np.load(pred_path, allow_pickle=False) as pred:
                        np.testing.assert_array_equal(pred['indices'], target)
                        np.testing.assert_array_equal(pred['labels'], stats['labels'][target])
                        np.testing.assert_allclose(cpu_logits, pred['scores'], rtol=2e-5, atol=2e-5)
                        np.testing.assert_array_equal(cpu_logits.argmax(1), pred['predictions'])
                        ba, f1, matrix = integer_metrics(pred['labels'], pred['predictions'])
                        expected = next(r for r in report['methods'][method]['per_person'] if r['person'] == fold['target'])
                        saved_row = next(r for r in expected['per_seed'] if r['seed'] == seed)
                        if matrix != saved_row['confusion']:
                            raise ValueError('Integer confusion mismatch')
                        np.testing.assert_allclose([ba, f1], [saved_row['ba'], saved_row['macro_f1']], rtol=0, atol=1e-14)
                        np.testing.assert_allclose(f1, f1_score(pred['labels'], pred['predictions'], average='macro'), rtol=0, atol=1e-14)
                        errors.append(float(np.max(np.abs(cpu_logits-pred['scores']))))
                        checked += len(target)
                    val_ba = mean_person_ba(stats['labels'][validation], network_logits(model, val_x).argmax(1), stats['subjects'][validation])
                    np.testing.assert_allclose(val_ba, h['best_source_validation_ba'] if state_name == 'best' else h['averaged_source_validation_ba'], rtol=0, atol=1e-14)
                checkpoint_checks += 1
        print('AUDIT_PERSON', fold['target'], flush=True)
    if digest(FROZEN) != read(output/'lock.json')['frozen_package_sha256']:
        raise ValueError('Formal release changed')
    save(output/'verification.json', {'verified_at_local': datetime.now().isoformat(), 'passed': True,
                                     'source_checkpoints_checked': checkpoint_checks,
                                     'new_prediction_classes_recomputed': checked,
                                     'cpu_gpu_max_abs_logits_error': max(errors),
                                     'classes_exact': True, 'source_bn_and_average_reconstructed': True,
                                     'weights_lag_bounds_and_source_selection_checked': True,
                                     'source_input_hashes_unchanged': True, 'formal_release_unchanged': True,
                                     'confirmation_eeg_read': False, 'results_sha256': digest(output/'results.json')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'train', 'evaluate', 'verify'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    {'prepare': prepare, 'train': train, 'evaluate': evaluate, 'verify': verify}[args.action](args.output)


if __name__ == '__main__':
    main()

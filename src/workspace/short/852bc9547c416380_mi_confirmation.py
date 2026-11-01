"""Once-only independent12 confirmation of the already selected fixed8 EEGNet."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import time

# Import Torch before MNE/SciPy on this Windows workstation.
from mi_comparison_models import (torch, EEGNetSmall, configure_torch, channel_scaler,
                                  normalized_tensor, train_network, network_logits)
import numpy as np
from sklearn.metrics import confusion_matrix
from threadpoolctl import threadpool_limits

from cho2017_data import DATA, FIXED, hashes, listing, fetch, load_subject
from cho2017_adaptation import (alignment_reference, align_covariances, log_power_ratio,
                               fit, features)
from cho2017_training_diagnostic import save, save_fitted
from mi_model_comparison import load_run, waveform_and_statistics, FROZEN
from mi_physionet_evaluate import subject_metrics, bootstrap_ci

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / 'mi_confirmation_protocol.json'
OUTPUT = HERE / 'output/mi_confirmation_20261001'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def source_split(people):
    if len(set(people)) != 30:
        raise ValueError('Exactly30 original source people required')
    ranked = sorted(people, key=lambda p: hashlib.sha256(
        f'mi-confirmation-20261001:{p}'.encode()).digest())
    return sorted(ranked[3:]), sorted(ranked[:3])


def checked_protocol():
    p = read_json(PROTOCOL)
    original = read_json(HERE / p['original_protocol'])
    selected = read_json(HERE / p['selected_architecture_protocol'])
    evidence = read_json(HERE / p['selected_evidence'])
    fitting, validation = source_split(original['train_subjects'])
    if (p['fit_people'] != fitting or p['validation_people'] != validation
            or p['confirmation_people'] != original['confirmation_subjects']
            or p['former_development_excluded'] != original['development_subjects']
            or p['channels'] != list(FIXED) or selected['channels'] != list(FIXED)
            or selected['eegnet']['seeds'] != [42, 43, 44] or p['deployment_seed'] != 42
            or evidence['selected_for_later_confirmation'] != 'C2_EEGNet_SMALL'
            or evidence['confirmation_eeg_read']
            or hashes(HERE / p['selected_evidence'])['sha256'] != p['selected_evidence_sha256']
            or p['control_enabled'] or p['production_changes_allowed']):
        raise ValueError('Frozen source/target isolation, choice or safety changed')
    groups = [set(p[k]) for k in ('fit_people', 'validation_people',
                                  'confirmation_people', 'former_development_excluded')]
    if any(groups[i] & groups[j] for i in range(4) for j in range(i + 1, 4)):
        raise ValueError('Person overlap')
    if set.union(*groups) != set(range(1, 53)) or len(groups[2]) != 12:
        raise ValueError('All52 people must have exactly one role')
    return p, original, selected


def freeze_paths():
    return [Path(__file__), PROTOCOL, HERE / 'MI_CONFIRMATION_PLAN.md',
            HERE / 'test_mi_confirmation.py', HERE / 'mi_comparison_models.py',
            HERE / 'mi_model_comparison.py', HERE / 'mi_model_comparison_protocol.json',
            HERE / 'cho2017_protocol.json', HERE / 'cho2017_data.py',
            HERE / 'cho2017_features.py', HERE / 'cho2017_adaptation.py',
            HERE / 'cho2017_training_diagnostic.py', HERE / 'cho2017_training_diagnostic_protocol.json',
            HERE / 'mi_spatial_development.py', HERE / 'mi_physionet_evaluate.py',
            HERE.parent / 'pynq_guardianloop/mi_spatial.py',
            HERE.parent / 'pynq_guardianloop/mi_features.py',
            HERE.parent / 'pynq_guardianloop/cyton_sqi.py']


def lock():
    p, _, selected = checked_protocol()
    OUTPUT.mkdir(exist_ok=False)
    snapshot = OUTPUT / 'code_snapshot'
    snapshot.mkdir()
    for path in freeze_paths():
        shutil.copy2(path, snapshot / path.name)
    save(OUTPUT / 'protocol.json', p)
    save(OUTPUT / 'network_config.json', selected['eegnet'])
    save(OUTPUT / 'lock.json', {
        'locked_at_local': datetime.now().isoformat(), 'confirmation_eeg_read': False,
        'code_sha256': {str(path): hashes(path)['sha256'] for path in freeze_paths()},
        'source_documents_sha256': {str(path): hashes(path)['sha256']
            for path in (DATA / 'source_docs').iterdir() if path.is_file()},
        'frozen_release_sha256': hashes(FROZEN)['sha256'],
        'software': {'torch': torch.__version__, 'numpy': np.__version__},
        'compute': selected['compute'], 'cuda_device': torch.cuda.get_device_name(0),
        'board_accessed': False, 'control_enabled': False})
    print('LOCKED_BEFORE_CONFIRMATION_EEG', p['confirmation_people'], flush=True)


def checked_lock():
    p, original, selected = checked_protocol()
    locked = read_json(OUTPUT / 'lock.json')
    if read_json(OUTPUT / 'protocol.json') != p:
        raise ValueError('Protocol changed after lock')
    for mapping in ('code_sha256', 'source_documents_sha256'):
        for name, digest in locked[mapping].items():
            if hashes(Path(name))['sha256'] != digest:
                raise ValueError('Frozen source changed: ' + name)
    return p, original, selected


def cache_indices(stats, p):
    fit_idx = np.flatnonzero(np.isin(stats['subjects'], p['fit_people']))
    val_idx = np.flatnonzero(np.isin(stats['subjects'], p['validation_people']))
    if (set(fit_idx) & set(val_idx) or len(fit_idx) + len(val_idx) != len(stats['subjects'])
            or not len(fit_idx) or not len(val_idx)):
        raise ValueError('Source cache contains forbidden people or overlapping trials')
    return fit_idx, val_idx


def train():
    p, _, selected = checked_lock()
    if (OUTPUT / 'confirmation_access.json').exists():
        raise RuntimeError('Confirmation already opened; source training forbidden')
    _, stats, waves, _ = load_run(HERE / p['source_cache'])
    fitting, validation = cache_indices(stats, p)
    configure_torch(selected['compute'])
    device = torch.device(selected['compute']['device'])
    if not torch.cuda.is_available():
        raise RuntimeError('Frozen CUDA compute unavailable')
    mean, scale = channel_scaler(waves[fitting])
    train_x = normalized_tensor(waves[fitting], mean, scale, device)
    val_x = normalized_tensor(waves[validation], mean, scale, device)
    folder = OUTPUT / 'source_models'
    folder.mkdir(exist_ok=True)
    for seed in selected['eegnet']['seeds']:
        path = folder / f'seed{seed}.pt'
        history_path = folder / f'seed{seed}.json'
        if path.exists():
            if not history_path.exists():
                raise RuntimeError('Incomplete checkpoint pair preserved')
            print('SOURCE_MODEL_ALREADY_FROZEN', seed, flush=True)
            continue
        def progress(epoch, best_epoch, ba, seconds):
            print('SOURCE_ONLY', seed, epoch, 'best', best_epoch, 'valBA', round(ba, 4),
                  'seconds', round(seconds, 1), flush=True)
        model, history = train_network(train_x, stats['labels'][fitting], val_x,
            stats['labels'][validation], stats['subjects'][validation],
            selected['eegnet'], seed, device, progress)
        checkpoint = {'state_dict': {k: v.detach().cpu() for k, v in model.state_dict().items()},
            'config': selected['eegnet'], 'source_mean': mean.tolist(), 'source_scale': scale.tolist(),
            'metadata': {'seed': seed, 'fit_people': p['fit_people'],
                'validation_people': p['validation_people'], 'confirmation_labels_used': False,
                'control_enabled': False, 'promotion_gate_passed': False}}
        torch.save(checkpoint, path)
        save(history_path, history)
        print('SOURCE_MODEL_FROZEN', seed, 'best', history['best_epoch'], flush=True)
        del model
    baseline_path = folder / 'B1.npz'
    if not baseline_path.exists():
        covs = stats['covariances'].copy()
        for person in p['fit_people']:
            mask = stats['subjects'] == person
            _, whitening = alignment_reference(covs[mask, 2], stats['order'][mask])
            covs[mask, 2] = align_covariances(covs[mask, 2], whitening)
        with threadpool_limits(limits=1):
            fitted = fit(covs[fitting], stats['log_power_ratio'][fitting],
                         stats['labels'][fitting], 'EA_CSP_ERD_LDA')
        save_fitted(baseline_path, fitted, {'fit_people': p['fit_people'],
            'validation_people_not_fitted': p['validation_people'], 'control_enabled': False})
    locked_models = {path.name: hashes(path)['sha256'] for path in folder.iterdir() if path.is_file()}
    complete = OUTPUT / 'source_training_complete.json'
    report = {'models_sha256': locked_models, 'source_trial_counts': {
        'fit': len(fitting), 'validation': len(validation)},
        'mean': mean.tolist(), 'scale': scale.tolist(),
        'source_cache_hashes': read_json(HERE / p['source_cache'] / 'provenance.json')['cache_sha256'],
        'confirmation_eeg_read': False, 'completed_at_local': datetime.now().isoformat()}
    if complete.exists():
        if read_json(complete)['models_sha256'] != locked_models:
            raise ValueError('Source models changed after completion')
    else:
        save(complete, report)
    print('ALL_SOURCE_MODELS_COMPLETE_BEFORE_TARGET', report['source_trial_counts'], flush=True)


def checked_models():
    p, original, selected = checked_lock()
    trained = read_json(OUTPUT / 'source_training_complete.json')
    for name, digest in trained['models_sha256'].items():
        if hashes(OUTPUT / 'source_models' / name)['sha256'] != digest:
            raise ValueError('Source checkpoint changed after freeze')
    return p, original, selected, trained


def download():
    p, _, _, _ = checked_models()
    sources = listing(DATA)
    needed = sum(sources[f'mat_data/s{person:02d}.mat']['bytes']
                 for person in p['confirmation_people'] if not (DATA / f's{person:02d}.mat').exists())
    if shutil.disk_usage(DATA).free < needed + 2 * 1024 ** 3:
        raise RuntimeError('Download would violate2GiB disk reserve')
    results, failures = [], []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch, person, DATA, sources, True): person
                   for person in p['confirmation_people']}
        for future in as_completed(futures):
            person = futures[future]
            try:
                results.append(future.result())
            except (RuntimeError, ValueError, OSError) as error:
                failures.append({'subject': person, 'error': str(error)})
                print('DOWNLOAD_FAILED', person, str(error), flush=True)
            save(OUTPUT / 'download_progress.json', {'verified': results, 'failures': failures})
            print('DOWNLOAD_VERIFIED', person, len(results), '/12', flush=True)
    if failures:
        raise RuntimeError('Incomplete transfer; retained files can be resumed without reading EEG')
    save(OUTPUT / 'download_manifest.json', sorted(results, key=lambda row: row['subject']))


def extract():
    p, original, _, trained = checked_models()
    if (OUTPUT / 'confirmation_cache.npz').exists():
        raise RuntimeError('Completed confirmation cache preserved; do not re-extract')
    manifest = read_json(OUTPUT / 'download_manifest.json')
    if [row['subject'] for row in manifest] != p['confirmation_people']:
        raise ValueError('All12 verified original target objects required')
    access_path = OUTPUT / 'confirmation_access.json'
    if not access_path.exists():
        save(access_path, {'first_eeg_access_at_local': datetime.now().isoformat(),
                          'source_training_completed_at': trained['completed_at_local'],
                          'protocol_sha256': hashes(PROTOCOL)['sha256'],
                          'note': 'These12 EEGs cease to be blind on this access; no source retraining allowed'})
    waves, covariances, baselines, tasks, rows = [], [], [], [], []
    for person, source in zip(p['confirmation_people'], manifest):
        if hashes(DATA / f's{person:02d}.mat')['sha256'] != source['sha256']:
            raise ValueError('Downloaded confirmation object changed')
        item = load_subject(person, DATA)
        for trial, samples in enumerate(item.samples):
            wave, cov, baseline, task = waveform_and_statistics(samples, item.cue_sample, original)
            waves.append(wave); covariances.append(cov); baselines.append(baseline); tasks.append(task)
            rows.append({'subject': person, 'original_order': trial, 'label': int(item.labels[trial]),
                         'original_sequence_key': int(item.original_keys[trial]),
                         'class_trial_index_one_based': int(item.class_trial_indices[trial]) + 1,
                         'cue_sample': item.cue_sample, 'voltage_bad': bool(item.voltage_bad[trial]),
                         'emg_bad': bool(item.emg_bad[trial])})
        print('CONFIRMATION_EXTRACTED', person, len(item.labels), flush=True)
        del item
    baseline, task = np.stack(baselines), np.stack(tasks)
    values = {'waves': np.stack(waves), 'covariances': np.stack(covariances),
        'log_power_ratio': log_power_ratio(baseline, task),
        'labels': np.array([r['label'] for r in rows]),
        'subjects': np.array([r['subject'] for r in rows]),
        'order': np.array([r['original_order'] for r in rows])}
    np.savez_compressed(OUTPUT / 'confirmation_cache.npz', **values)
    save(OUTPUT / 'trial_manifest.json', rows)
    save(OUTPUT / 'extraction.json', {'subjects_eeg_read': p['confirmation_people'],
        'trials': len(rows), 'trials_discarded': 0,
        'author_flagged_retained': sum(r['voltage_bad'] or r['emg_bad'] for r in rows),
        'waveform_shape': list(values['waves'].shape), 'former_development_eeg_read': False,
        'cache_sha256': hashes(OUTPUT / 'confirmation_cache.npz')['sha256'],
        'trial_manifest_sha256': hashes(OUTPUT / 'trial_manifest.json')['sha256'],
        'completed_at_local': datetime.now().isoformat()})


def load_target():
    p, _, selected, trained = checked_models()
    info = read_json(OUTPUT / 'extraction.json')
    if info['subjects_eeg_read'] != p['confirmation_people'] or info['trials_discarded']:
        raise ValueError('Confirmation extraction scope invalid')
    for name, key in (('confirmation_cache.npz', 'cache_sha256'), ('trial_manifest.json', 'trial_manifest_sha256')):
        if hashes(OUTPUT / name)['sha256'] != info[key]:
            raise ValueError('Target cache changed')
    with np.load(OUTPUT / 'confirmation_cache.npz', allow_pickle=False) as cache:
        values = {key: cache[key].copy() for key in cache.files}
    if sorted(set(values['subjects'])) != p['confirmation_people']:
        raise ValueError('Unexpected target identity')
    return p, selected, trained, values


def aggregate(rows, bootstrap_seed):
    ba = np.array([r['balanced_accuracy'] for r in rows])
    return {'mean_subject_balanced_accuracy': float(ba.mean()),
            'subject_bootstrap_95_ci': bootstrap_ci(ba, bootstrap_seed),
            'between_subject_sd': float(ba.std(ddof=1)),
            'mean_subject_macro_f1': float(np.mean([r['macro_f1'] for r in rows])),
            'per_subject': rows}


def paired(candidate, reference, settings):
    if [r['subject'] for r in candidate] != [r['subject'] for r in reference]:
        raise ValueError('Paired people mismatch')
    differences = np.array([a['balanced_accuracy'] - b['balanced_accuracy']
                            for a, b in zip(candidate, reference)])
    rng = np.random.default_rng(settings['seed'])
    boot = differences[rng.integers(0, len(differences),
                    size=(settings['draws'], len(differences)))].mean(axis=1)
    return {'mean_ba_gain': float(differences.mean()),
            'paired_bootstrap_95_ci': np.quantile(boot, [.025, .975]).tolist(),
            'per_subject_gain': differences.tolist()}


def gates(primary, comparison, artifact, p):
    g, a = p['confirmation_gate'], p['artifact_gate']
    checks = {'primary_mean': primary['mean_subject_balanced_accuracy'] >= g['mean_ba_at_least'],
        'primary_absolute_interval': primary['subject_bootstrap_95_ci'][0] > g['absolute_ci_lower_greater_than'],
        'paired_gain': comparison['mean_ba_gain'] >= g['paired_gain_at_least'],
        'paired_interval': comparison['paired_bootstrap_95_ci'][0] > g['paired_ci_lower_greater_than'],
        'seed42_mean': artifact['mean_subject_balanced_accuracy'] >= a['mean_ba_at_least'],
        'seed42_absolute_interval': artifact['subject_bootstrap_95_ci'][0] > a['absolute_ci_lower_greater_than']}
    return {**{key: bool(value) for key, value in checks.items()},
            'confirmation_gate_passed': bool(all(checks[k] for k in list(checks)[:4])),
            'artifact_gate_passed': bool(checks['seed42_mean'] and checks['seed42_absolute_interval']),
            'arm_eligible': bool(all(checks.values()))}


def detailed_rows(labels, predictions, subjects):
    rows = subject_metrics(labels, predictions, subjects)
    for row in rows:
        mask = subjects == row['subject']
        row['confusion_matrix'] = confusion_matrix(labels[mask], predictions[mask], labels=[0, 1]).tolist()
        row['class_counts'] = np.bincount(labels[mask], minlength=2).tolist()
    return rows


def report_from_saved(p, target):
    scored = np.flatnonzero(target['order'] >= 60)
    methods, seeded_rows, prediction_hashes = {}, {}, {}
    for name in ('B1', 'seed42', 'seed43', 'seed44'):
        path = OUTPUT / 'predictions' / f'{name}.npz'
        with np.load(path, allow_pickle=False) as saved:
            np.testing.assert_array_equal(saved['indices'], scored)
            np.testing.assert_array_equal(saved['labels'], target['labels'][scored])
            scores, predictions = saved['scores'], saved['predictions']
            expected = (scores > 0).astype(int) if name == 'B1' else scores.argmax(axis=1)
            np.testing.assert_array_equal(predictions, expected)
            rows = detailed_rows(saved['labels'], predictions, target['subjects'][scored])
        seeded_rows[name] = rows
        methods[name] = aggregate(rows, p['bootstrap']['seed'])
        prediction_hashes[path.name] = hashes(path)['sha256']
    primary_rows = []
    for index, person in enumerate(p['confirmation_people']):
        repetitions = [seeded_rows[f'seed{seed}'][index] for seed in (42, 43, 44)]
        primary_rows.append({'subject': person, 'trials': repetitions[0]['trials'],
            'balanced_accuracy': float(np.mean([r['balanced_accuracy'] for r in repetitions])),
            'macro_f1': float(np.mean([r['macro_f1'] for r in repetitions])),
            'per_seed': [dict(seed=seed, **row) for seed, row in zip((42, 43, 44), repetitions)]})
    methods['EEGNet_three_seed_mean'] = aggregate(primary_rows, p['bootstrap']['seed'])
    comparison = paired(primary_rows, methods['B1']['per_subject'], p['bootstrap'])
    decision = gates(methods['EEGNet_three_seed_mean'], comparison, methods['seed42'], p)
    return {'scope': 'Once-only independent12 public-data confirmation,not Cyton/idle/control accuracy',
        'methods': methods, 'paired_against_B1': comparison, 'decision': decision,
        'scored_trials': len(scored), 'all_extracted_trials': len(target['labels']),
        'scored_class_counts': np.bincount(target['labels'][scored], minlength=2).tolist(),
        'prediction_sha256': prediction_hashes, 'control_enabled': False,
        'production_deployed': False, 'confirmation_people_no_longer_blind': p['confirmation_people']}


def evaluate():
    if (OUTPUT / 'results.json').exists():
        raise RuntimeError('Confirmation already scored; preserve original result')
    p, selected, _, target = load_target()
    configure_torch(selected['compute'])
    scored = np.flatnonzero(target['order'] >= 60)
    folder = OUTPUT / 'predictions'
    folder.mkdir(exist_ok=True)
    numeric = {}
    for seed in selected['eegnet']['seeds']:
        path = folder / f'seed{seed}.npz'
        if path.exists():
            continue
        checkpoint = torch.load(OUTPUT / 'source_models' / f'seed{seed}.pt',
                                map_location='cpu', weights_only=True)
        model = EEGNetSmall(checkpoint['config']).to(selected['compute']['device'])
        model.load_state_dict(checkpoint['state_dict'])
        mean, scale = np.array(checkpoint['source_mean']), np.array(checkpoint['source_scale'])
        values = normalized_tensor(target['waves'][scored], mean, scale, selected['compute']['device'])
        logits = network_logits(model, values)
        cpu_model = EEGNetSmall(checkpoint['config'])
        cpu_model.load_state_dict(checkpoint['state_dict'])
        cpu_logits = network_logits(cpu_model, values.cpu())
        np.testing.assert_allclose(cpu_logits, logits, rtol=1e-5, atol=1e-5)
        np.testing.assert_array_equal(cpu_logits.argmax(axis=1), logits.argmax(axis=1))
        np.savez_compressed(path, indices=scored, labels=target['labels'][scored],
            scores=logits, cpu_scores=cpu_logits, predictions=logits.argmax(axis=1))
        numeric[f'seed{seed}_cpu_gpu_max_abs_error'] = float(np.max(np.abs(cpu_logits - logits)))
        print('CONFIRMATION_PREDICTIONS_FROZEN', seed, len(scored), flush=True)
    path = folder / 'B1.npz'
    if not path.exists():
        covs = target['covariances'].copy()
        for person in p['confirmation_people']:
            mask = target['subjects'] == person
            _, whitening = alignment_reference(covs[mask, 2], target['order'][mask])
            covs[mask, 2] = align_covariances(covs[mask, 2], whitening)
        with np.load(OUTPUT / 'source_models/B1.npz', allow_pickle=False) as fitted:
            vector = features(covs[scored], target['log_power_ratio'][scored],
                              'EA_CSP_ERD_LDA', fitted['filters'])
            scores = ((vector - fitted['mean']) / fitted['scale']) @ fitted['coef'] + fitted['intercept']
        if not np.isfinite(scores).all():
            raise ValueError('Nonfinite baseline output')
        np.savez_compressed(path, indices=scored, labels=target['labels'][scored],
                            scores=scores, predictions=(scores > 0).astype(int))
    report = report_from_saved(p, target)
    report['numeric_checks'] = numeric
    report['completed_at_local'] = datetime.now().isoformat()
    report['frozen_release_sha256_after'] = hashes(FROZEN)['sha256']
    if report['frozen_release_sha256_after'] != read_json(OUTPUT / 'lock.json')['frozen_release_sha256']:
        raise ValueError('Protected release changed')
    save(OUTPUT / 'results.json', report)
    print(json.dumps({'means': {name: m['mean_subject_balanced_accuracy']
        for name, m in report['methods'].items()}, 'paired': report['paired_against_B1'],
        'decision': report['decision']}, indent=2), flush=True)


def verify():
    p, selected, _, target = load_target()
    actual = read_json(OUTPUT / 'results.json')
    expected = report_from_saved(p, target)
    for key in expected:
        if actual[key] != expected[key]:
            raise ValueError('Saved metrics/decision disagree: ' + key)
    configure_torch(selected['compute'])
    scored = np.flatnonzero(target['order'] >= 60)
    maximum_error = 0.0
    # Verify source checkpoint selection on source-only EEG, never fit again.
    _, source_stats, source_waves, _ = load_run(HERE / p['source_cache'])
    _, validation = cache_indices(source_stats, p)
    for seed in selected['eegnet']['seeds']:
        checkpoint = torch.load(OUTPUT / 'source_models' / f'seed{seed}.pt',
                                map_location='cpu', weights_only=True)
        model = EEGNetSmall(checkpoint['config'])
        model.load_state_dict(checkpoint['state_dict'])
        values = normalized_tensor(target['waves'][scored], np.array(checkpoint['source_mean']),
                                   np.array(checkpoint['source_scale']), 'cpu')
        logits = network_logits(model, values)
        with np.load(OUTPUT / 'predictions' / f'seed{seed}.npz', allow_pickle=False) as saved:
            np.testing.assert_allclose(logits, saved['scores'], rtol=1e-5, atol=1e-5)
            np.testing.assert_array_equal(logits.argmax(axis=1), saved['predictions'])
            maximum_error = max(maximum_error, float(np.max(np.abs(logits - saved['scores']))))
        history = read_json(OUTPUT / 'source_models' / f'seed{seed}.json')
        ba = [row['source_validation_mean_person_ba'] for row in history['history']]
        if history['best_epoch'] != int(np.argmax(ba)) + 1:
            raise ValueError('Checkpoint does not use earliest source-validation maximum')
        validation_x = normalized_tensor(source_waves[validation], np.array(checkpoint['source_mean']),
                                         np.array(checkpoint['source_scale']), 'cpu')
        validation_logits = network_logits(model, validation_x)
        validation_rows = detailed_rows(source_stats['labels'][validation], validation_logits.argmax(axis=1),
                                       source_stats['subjects'][validation])
        validation_ba = float(np.mean([row['balanced_accuracy'] for row in validation_rows]))
        if abs(validation_ba - history['source_validation_mean_person_ba']) > 1e-12:
            raise ValueError('Reloaded source checkpoint validation BA differs')
    covs = target['covariances'].copy()
    for person in p['confirmation_people']:
        mask = target['subjects'] == person
        _, whitening = alignment_reference(covs[mask, 2], target['order'][mask])
        covs[mask, 2] = align_covariances(covs[mask, 2], whitening)
    with np.load(OUTPUT / 'source_models/B1.npz', allow_pickle=False) as fitted:
        vector = features(covs[scored], target['log_power_ratio'][scored],
                          'EA_CSP_ERD_LDA', fitted['filters'])
        scores = ((vector - fitted['mean']) / fitted['scale']) @ fitted['coef'] + fitted['intercept']
    with np.load(OUTPUT / 'predictions/B1.npz', allow_pickle=False) as saved:
        np.testing.assert_allclose(scores, saved['scores'], rtol=1e-10, atol=1e-10)
        np.testing.assert_array_equal((scores > 0).astype(int), saved['predictions'])
    save(OUTPUT / 'verification.json', {'all_metrics_and_gates_recomputed': True,
        'frozen_code_and_models_unchanged': True, 'source_target_people_disjoint': True,
        'source_validation_checkpoint_ba_recomputed': True, 'baseline_scores_recomputed': True,
        'predictions_recomputed': int(len(scored) * 4),
        'cpu_gpu_max_abs_error': maximum_error, 'results_sha256': hashes(OUTPUT / 'results.json')['sha256'],
        'confirmation_gate_passed': actual['decision']['confirmation_gate_passed'],
        'arm_eligible': actual['decision']['arm_eligible'], 'board_accessed': False,
        'control_enabled': False, 'completed_at_local': datetime.now().isoformat()})
    print('INDEPENDENT_SAVED_RESULT_VERIFICATION_COMPLETE', len(scored) * 4, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('lock', 'train', 'download', 'extract', 'evaluate', 'verify'))
    args = parser.parse_args()
    globals()[args.action]()


if __name__ == '__main__':
    main()

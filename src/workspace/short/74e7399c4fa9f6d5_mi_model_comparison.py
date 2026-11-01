"""Five frozen training-only MI conditions; never deploy or read held-out groups."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import time

# On Windows, load PyTorch DLLs before the MNE/SciPy dependency stack.
from mi_comparison_models import (FB_INDICES, split_people, fit_selected_fb, selected_fb_scores,
                                  configure_torch, channel_scaler, normalized_tensor, train_network,
                                  network_logits, EEGNetSmall, torch)
import numpy as np
import scipy
import sklearn
from sklearn.metrics import confusion_matrix
from threadpoolctl import threadpool_limits

from cho2017_data import DATA, FIXED, hashes
from cho2017_features import _filtered_epoch, normalized_covariance
from cho2017_training_diagnostic import validate_protocol, read_training_person, save, save_fitted
from cho2017_adaptation import alignment_reference, align_covariances, fit as fit_adaptation, predict as predict_adaptation
from mi_spatial_development import fit as fit_spatial, predict as predict_spatial
from mi_physionet_evaluate import bootstrap_ci, subject_metrics

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / 'mi_model_comparison_protocol.json'
DEFAULT_OUTPUT = HERE / 'output/mi_model_comparison_20261001'
FROZEN = Path('D:/ican/handoff/GuardianLoop_FROZEN_20261001.zip')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def checked_protocol():
    protocol = read_json(PROTOCOL)
    original = read_json(HERE / protocol['original_protocol'])
    allowed = validate_protocol(original, read_json(HERE / protocol['training_scope_protocol']))
    if (protocol['participants'] != allowed or protocol['channels'] != list(FIXED)
            or protocol['target_prefix_unscored_trials'] != 60
            or protocol['source_fit_people_per_fold'] != 26 or protocol['source_validation_people_per_fold'] != 3
            or protocol['fbcsp_selection']['band_indices'] != FB_INDICES):
        raise ValueError('Frozen montage, people, folds or bands changed')
    expected = HERE / 'output/cho2017_training_diagnostic_20261001/training_statistics.npz'
    if (HERE / protocol['statistics_cache']).resolve() != expected.resolve():
        raise ValueError('Only original training-only statistics allowed')
    return protocol, original, allowed


def waveform_and_statistics(samples, cue, original):
    bands, start, stop = _filtered_epoch(samples, cue, original)
    baseline_stop = round(cue/original['source_rate_hz']*250)
    covs = np.stack([normalized_covariance(band[start:stop], expected_samples=500) for band in bands])
    baseline = np.stack([np.var(band[baseline_stop-250:baseline_stop], axis=0, ddof=1) for band in bands])
    task = np.stack([np.var(band[start:stop], axis=0, ddof=1) for band in bands])
    waveform64 = bands[2][start:stop].T.copy()
    return waveform64.astype(np.float32), covs, baseline, task


def fold_indices(subjects, order, fold):
    fitting = np.flatnonzero(np.isin(subjects, fold['fit_people']))
    validation = np.flatnonzero(np.isin(subjects, fold['validation_people']))
    target = np.flatnonzero((subjects == fold['target']) & (order >= 60))
    sets = [set(fitting), set(validation), set(target)]
    if any(sets[i] & sets[j] for i in range(3) for j in range(i+1, 3)) or not all(sets):
        raise ValueError('Train/validation/target indices overlap or empty')
    return fitting, validation, target


def prepare(root, output):
    protocol, original, allowed = checked_protocol()
    old = HERE / protocol['statistics_cache']
    provenance = read_json(old.parent / 'provenance.json')
    if (provenance['subjects_actually_read'] != allowed or provenance['former_development_eeg_read']
            or provenance['confirmation_eeg_read'] or provenance['old_mixed_feature_cache_loaded']):
        raise ValueError('Old cache scope invalid')
    old_hashes = read_json(old.parent / 'source_sha256.json')
    manifest = read_json(old.parent / 'trial_manifest.json')
    with np.load(old, allow_pickle=False) as values:
        statistics = {key: values[key].copy() for key in values.files}
    if len(manifest) != 6080 or sorted(set(statistics['subjects'])) != allowed:
        raise ValueError('All original6080 training trials required')
    output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), HERE/'mi_comparison_models.py', PROTOCOL, HERE/'test_mi_model_comparison.py',
             HERE/'MI_NEXT_MODEL_COMPARISON_PLAN.md', HERE/'cho2017_protocol.json',
             HERE/'cho2017_training_diagnostic_protocol.json', HERE/'cho2017_training_diagnostic.py',
             HERE/'cho2017_features.py', HERE/'cho2017_data.py', HERE/'cho2017_adaptation.py',
             HERE/'mi_spatial_development.py', HERE/'mi_physionet_evaluate.py',
             HERE.parent/'pynq_guardianloop/mi_spatial.py', HERE.parent/'pynq_guardianloop/mi_features.py',
             HERE.parent/'pynq_guardianloop/cyton_sqi.py']
    snapshot = output/'code_snapshot'
    snapshot.mkdir()
    for path in paths:
        shutil.copy2(path, snapshot/path.name)
    folds = []
    for person in allowed:
        fitting, validation = split_people(allowed, person)
        folds.append({'target': person, 'fit_people': fitting, 'validation_people': validation})
    save(output/'fold_manifest.json', folds)
    save(output/'protocol.json', protocol)
    info = {'started_at_local': datetime.now().isoformat(), 'subjects_actually_read': [],
            'former_development_eeg_read': False, 'confirmation_eeg_read': False,
            'old_mixed_feature_cache_loaded': False, 'board_accessed': False,
            'protocol_sha256': hashes(PROTOCOL)['sha256'],
            'source_sha256': {str(p): hashes(p)['sha256'] for p in paths},
            'original_statistics_sha256': hashes(old)['sha256'],
            'frozen_package_sha256_before': hashes(FROZEN)['sha256'],
            'software': {'torch': torch.__version__, 'numpy': np.__version__, 'scipy': scipy.__version__,
                         'sklearn': sklearn.__version__},
            'cuda_device': torch.cuda.get_device_name(0), 'cuda_runtime': torch.version.cuda,
            'timing_scope': 'Windows workstation, not Z15 ARM/PL',
            'statistics_comparison_max_abs_error': 0.0}
    save(output/'provenance.json', info)
    start = time.monotonic()
    waves = np.empty((6080, 8, 500), dtype=np.float32)
    for person in allowed:
        indices = np.flatnonzero(statistics['subjects'] == person)
        item = read_training_person(person, root, allowed)
        if hashes(root/f's{person:02d}.mat')['sha256'] != old_hashes[f's{person:02d}.mat']:
            raise ValueError('Original source changed: '+str(person))
        if not np.array_equal(statistics['labels'][indices], item.labels):
            raise ValueError('Source/cache labels differ')
        for trial, index in enumerate(indices):
            row = manifest[index]
            if (row['original_order'] != trial or row['original_sequence_key'] != int(item.original_keys[trial])
                    or row['cue_sample'] != item.cue_sample or row['voltage_bad'] != bool(item.voltage_bad[trial])
                    or row['emg_bad'] != bool(item.emg_bad[trial])
                    or row['class_trial_index_one_based'] != int(item.class_trial_indices[trial])+1):
                raise ValueError('Trial identity or flags changed')
            wave, cov, baseline, task = waveform_and_statistics(item.samples[trial], item.cue_sample, original)
            for actual, expected in ((cov, statistics['covariances'][index]),
                                     (baseline, statistics['baseline_variance'][index]),
                                     (task, statistics['task_variance'][index])):
                np.testing.assert_array_equal(actual, expected)
            waves[index] = wave
        info['subjects_actually_read'].append(person)
        save(output/'provenance.json', info)
        print('WAVE_CACHE', person, len(indices), flush=True)
        del item
    np.save(output/'waveforms.npy', waves, allow_pickle=False)
    np.savez_compressed(output/'statistics.npz', **statistics)
    save(output/'trial_manifest.json', manifest)
    info.update(cache_sha256={name: hashes(output/name)['sha256'] for name in
                             ('waveforms.npy','statistics.npz','trial_manifest.json','fold_manifest.json')},
                preparation_seconds=time.monotonic()-start, preparation_complete=True)
    save(output/'provenance.json', info)
    print('CACHE_COMPLETE', info['preparation_seconds'], flush=True)


def load_run(output):
    protocol, _, allowed = checked_protocol()
    info = read_json(output/'provenance.json')
    if (not info.get('preparation_complete') or info['protocol_sha256'] != hashes(PROTOCOL)['sha256']
            or info['subjects_actually_read'] != allowed):
        raise ValueError('Incomplete or changed run protocol')
    for path, digest in info['source_sha256'].items():
        if hashes(Path(path))['sha256'] != digest:
            raise ValueError('Code changed after locking: '+path)
    for name, digest in info['cache_sha256'].items():
        if hashes(output/name)['sha256'] != digest:
            raise ValueError('Run cache changed: '+name)
    with np.load(output/'statistics.npz', allow_pickle=False) as cache:
        statistics = {key: cache[key].copy() for key in cache.files}
    waves = np.load(output/'waveforms.npy', allow_pickle=False)
    folds = read_json(output/'fold_manifest.json')
    return protocol, statistics, waves, folds


def save_prediction(output, person, method, seed, indices, labels, scores, predictions, metadata):
    folder = output/'fold_predictions'
    folder.mkdir(exist_ok=True)
    path = folder/f's{person:02d}_{method}_seed{seed}.npz'
    if path.exists():
        raise RuntimeError('Preserve completed predictions: '+str(path))
    np.savez_compressed(path, indices=indices, labels=labels, scores=scores, predictions=predictions,
                        metadata=json.dumps(metadata, ensure_ascii=False))


def classical(output):
    protocol, stats, _, folds = load_run(output)
    params = output/'fold_parameters'
    params.mkdir(exist_ok=True)
    covs, ratios, labels, people, order = [stats[k] for k in ('covariances','log_power_ratio','labels','subjects','order')]
    aligned = covs.copy()
    for person in protocol['participants']:
        mask = people == person
        _, whitening = alignment_reference(covs[mask, 2], order[mask])
        aligned[mask, 2] = align_covariances(covs[mask, 2], whitening)
    start = time.monotonic()
    with threadpool_limits(limits=1):
        for fold in folds:
            train, _, target = fold_indices(people, order, fold)
            meta = {**fold, 'target_labels_used_for_fit': False, 'control_enabled': False,
                    'prefix_unscored_trials': 60, 'train_trials': len(train)}
            for name, values, method in (('B0_CSP_LDA', covs, 'CSP_LDA'),
                                         ('B1_EA_CSP_ERD_LDA', aligned, 'EA_CSP_ERD_LDA')):
                fitted = fit_adaptation(values[train], ratios[train], labels[train], method)
                pred, scores, error = predict_adaptation(values[target], ratios[target], fitted)
                save_fitted(params/f's{fold["target"]:02d}_{name}.npz', fitted, meta)
                save_prediction(output, fold['target'], name, 0, target, labels[target], scores, pred,
                                {**meta, 'portable_max_abs_error': error})
            fb = fit_spatial(covs[train], labels[train], 'FBCSP_LDA')
            pred, scores, error = predict_spatial(covs[target], 'FBCSP_LDA', fb)
            selected = fit_selected_fb(covs[train], labels[train], fb[0], protocol['fbcsp_selection'])
            for name, filters, scaler, classifier, positions, information in (
                ('B2_FBCSP_LDA', *fb, np.arange(5), np.empty(0)),
                ('C1_FBCSP_SELECTED', selected.filters, selected.scaler, selected.classifier,
                 selected.selected_positions, selected.band_mutual_information)):
                if name.startswith('C1'):
                    pred, scores, error = selected_fb_scores(covs[target], selected)
                np.savez_compressed(params/f's{fold["target"]:02d}_{name}.npz', filters=filters,
                                    mean=scaler.mean_, scale=scaler.scale_, coef=classifier.coef_[0],
                                    intercept=classifier.intercept_[0], selected_positions=positions,
                                    band_mutual_information=information, metadata=json.dumps(meta))
                save_prediction(output, fold['target'], name, 0, target, labels[target], scores, pred,
                                {**meta, 'portable_max_abs_error': error})
            print('CLASSICAL_FOLD_COMPLETE', fold['target'], flush=True)
    save(output/'classical_runtime.json', {'pc_seconds': time.monotonic()-start, 'board_accessed': False})


def neural(output):
    protocol, stats, waves, folds = load_run(output)
    configure_torch(protocol['compute'])
    if not torch.cuda.is_available():
        raise RuntimeError('Locked CUDA device unavailable; do not silently change compute protocol')
    device = torch.device(protocol['compute']['device'])
    folder = output/'network_checkpoints'
    folder.mkdir(exist_ok=True)
    for fold in folds:
        train, validation, target = fold_indices(stats['subjects'], stats['order'], fold)
        mean, scale = channel_scaler(waves[train])
        train_x = normalized_tensor(waves[train], mean, scale, device)
        validation_x = normalized_tensor(waves[validation], mean, scale, device)
        # Target normalized/forwarded only after source-only checkpoint selection below.
        for seed in protocol['eegnet']['seeds']:
            prefix = f's{fold["target"]:02d}_seed{seed}'
            if (output/'fold_predictions'/f's{fold["target"]:02d}_C2_EEGNet_SMALL_seed{seed}.npz').exists():
                print('SKIP_COMPLETE', prefix, flush=True)
                continue
            def progress(epoch, best_epoch, ba, seconds):
                print('SOURCE_VAL', prefix, epoch, 'best_epoch', best_epoch, 'BA', round(ba,4),
                      'seconds', round(seconds,1), flush=True)
            model, history = train_network(train_x, stats['labels'][train], validation_x,
                                           stats['labels'][validation], stats['subjects'][validation],
                                           protocol['eegnet'], seed, device, progress)
            checkpoint = {'state_dict': {key: value.detach().cpu() for key, value in model.state_dict().items()},
                          'config': protocol['eegnet'], 'source_mean': mean.tolist(), 'source_scale': scale.tolist(),
                          'metadata': {**fold, 'seed': seed, 'target_labels_used_for_selection': False,
                                       'promotion_gate_passed': False, 'control_enabled': False}}
            torch.save(checkpoint, folder/f'{prefix}.pt')
            save(folder/f'{prefix}.json', history)
            # Reload independently from on-disk checkpoint before touching target labels for metrics.
            restored = torch.load(folder/f'{prefix}.pt', map_location='cpu', weights_only=True)
            model2 = EEGNetSmall(restored['config']).to(device)
            model2.load_state_dict(restored['state_dict'])
            x = normalized_tensor(waves[target], np.array(restored['source_mean']), np.array(restored['source_scale']), device)
            logits = network_logits(model, x)
            reloaded = network_logits(model2, x)
            np.testing.assert_array_equal(logits, reloaded)
            save_prediction(output, fold['target'], 'C2_EEGNet_SMALL', seed, target, stats['labels'][target],
                            logits, logits.argmax(axis=1), {**fold, 'seed': seed,
                            'best_epoch': history['best_epoch'], 'source_validation_ba': history['source_validation_mean_person_ba'],
                            'checkpoint_reload_max_abs_error': float(np.max(np.abs(logits-reloaded)))})
            print('NETWORK_FOLD_COMPLETE', prefix, 'epochs', history['completed_epochs'], flush=True)
            del model, model2, x
        del train_x, validation_x


def paired(candidate, reference, settings):
    differences = np.array([c['balanced_accuracy']-r['balanced_accuracy'] for c,r in zip(candidate, reference)])
    rng = np.random.default_rng(settings['seed'])
    boot = differences[rng.integers(0,len(differences),size=(settings['draws'],len(differences)))].mean(axis=1)
    tail = (1-settings['paired_interval'])/2
    return {'mean_ba_gain': float(differences.mean()), 'paired_95_ci': np.quantile(boot,[.025,.975]).tolist(),
            'two_comparison_adjusted_97_5_ci': np.quantile(boot,[tail,1-tail]).tolist(),
            'people_improved': int((differences>0).sum()), 'people_declined': int((differences<0).sum()),
            'people_tied': int((differences==0).sum()),
            'per_person_gain': differences.tolist()}


def summarize(output):
    protocol, stats, _, folds = load_run(output)
    manifest = read_json(output/'trial_manifest.json')
    methods, prediction_hashes = {}, {}
    for method in protocol['methods']:
        rows = []
        for fold in folds:
            seeds = protocol['eegnet']['seeds'] if method == 'C2_EEGNet_SMALL' else [0]
            _, _, target = fold_indices(stats['subjects'], stats['order'], fold)
            repetitions = []
            for seed in seeds:
                path = output/'fold_predictions'/f's{fold["target"]:02d}_{method}_seed{seed}.npz'
                with np.load(path, allow_pickle=False) as prediction:
                    np.testing.assert_array_equal(prediction['indices'], target)
                    np.testing.assert_array_equal(prediction['labels'], stats['labels'][target])
                    row = subject_metrics(prediction['labels'], prediction['predictions'], stats['subjects'][target])[0]
                    row.update(seed=seed, confusion_matrix=confusion_matrix(prediction['labels'],prediction['predictions'],labels=[0,1]).tolist())
                    repetitions.append(row)
                prediction_hashes[path.name] = hashes(path)['sha256']
            rows.append({'subject': fold['target'], 'trials': len(target),
                         'balanced_accuracy': float(np.mean([r['balanced_accuracy'] for r in repetitions])),
                         'macro_f1': float(np.mean([r['macro_f1'] for r in repetitions])), 'per_seed': repetitions})
        values = np.array([row['balanced_accuracy'] for row in rows])
        methods[method] = {'mean_subject_balanced_accuracy': float(values.mean()),
                           'between_subject_sd': float(values.std(ddof=1)),
                           'subject_bootstrap_95_ci': bootstrap_ci(values,protocol['bootstrap']['seed']),
                           'mean_subject_macro_f1': float(np.mean([r['macro_f1'] for r in rows])), 'per_subject': rows}
    comparisons = {}
    for candidate in protocol['primary_candidates']:
        comparison = paired(methods[candidate]['per_subject'], methods[protocol['primary_reference']]['per_subject'], protocol['bootstrap'])
        gate = protocol['continuation_gate']
        comparison['continuation_gate_passed'] = bool(methods[candidate]['mean_subject_balanced_accuracy']>=gate['mean_ba_at_least']
                                                     and comparison['mean_ba_gain']>=gate['paired_gain_at_least']
                                                     and comparison['two_comparison_adjusted_97_5_ci'][0]>gate['adjusted_ci_lower_greater_than'])
        comparisons[candidate] = comparison
    passing = [m for m in comparisons if comparisons[m]['continuation_gate_passed']]
    selected = max(passing,key=lambda m: methods[m]['mean_subject_balanced_accuracy']) if passing else None
    report = {'scope': 'Training30 nested-person exploratory comparison,not independent confirmation or wearable accuracy',
              'protocol': protocol,'methods':methods,'paired_against_fixed_B1': comparisons,
              'secondary_C1_minus_B2': paired(methods['C1_FBCSP_SELECTED']['per_subject'], methods['B2_FBCSP_LDA']['per_subject'],protocol['bootstrap']),
              'passing_candidates': passing,'selected_for_later_confirmation':selected,
              'all_trials':len(manifest),'author_flagged_retained':sum(r['voltage_bad'] or r['emg_bad'] for r in manifest),
              'common_scored_trials':int((stats['order']>=60).sum()),'trials_discarded':0,
              'former_development_eeg_read':False,'confirmation_eeg_read':False,'board_accessed':False,
              'promotion_gate_passed':False,'control_enabled':False,'prediction_sha256':prediction_hashes,
              'frozen_package_sha256_after':hashes(FROZEN)['sha256'],'completed_at_local':datetime.now().isoformat()}
    if (output/'results.json').exists():
        raise RuntimeError('Existing results preserved')
    save(output/'results.json',report)
    print(json.dumps({'means':{m: methods[m]['mean_subject_balanced_accuracy'] for m in methods},
                      'passing':passing,'selected':selected},indent=2),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare','classical','neural','summarize'))
    parser.add_argument('--root',type=Path,default=DATA)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args()
    if args.action == 'prepare':
        prepare(args.root,args.output)
    else:
        {'classical':classical,'neural':neural,'summarize':summarize}[args.action](args.output)


if __name__ == '__main__':
    main()

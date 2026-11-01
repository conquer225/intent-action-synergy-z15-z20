"""One frozen source-local S&R experiment, reusing the original30-only cache."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil

from mi_segmentation import train_augmented
from mi_comparison_models import (EEGNetSmall, channel_scaler, configure_torch,
                                  normalized_tensor, network_logits, torch)
import numpy as np
from sklearn.metrics import confusion_matrix

from cho2017_data import hashes, FIXED
from cho2017_training_diagnostic import save
from mi_model_comparison import load_run, fold_indices, save_prediction, FROZEN
from mi_physionet_evaluate import bootstrap_ci, subject_metrics

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / 'mi_segmentation_protocol.json'
OUTPUT = HERE / 'output/mi_segmentation_20261001'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def prepare(output):
    protocol = read_json(PROTOCOL)
    baseline = HERE / protocol['baseline_run']
    old, stats, waves, folds = load_run(baseline)
    if (hashes(baseline/'results.json')['sha256'] != protocol['baseline_results_sha256']
            or protocol['channels'] != list(FIXED) or protocol['seeds'] != old['eegnet']['seeds']
            or len(stats['labels']) != 6080 or waves.shape != (6080,8,500)
            or not read_json(baseline/'audit.json')['audit_passed']):
        raise ValueError('Baseline, fixed montage or completed audit changed')
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output/'code_snapshot'; snapshot.mkdir()
    paths = [Path(__file__), HERE/'mi_segmentation.py', PROTOCOL,
             HERE/'test_mi_segmentation.py', HERE/'mi_segmentation_audit.py']
    for path in paths:
        shutil.copy2(path, snapshot/path.name)
    save(output/'protocol.json', protocol)
    save(output/'fold_manifest.json', folds)
    save(output/'provenance.json', {
        'locked_at_local': datetime.now().isoformat(),
        'source_sha256': {str(path): hashes(path)['sha256'] for path in paths},
        'baseline_provenance_sha256': hashes(baseline/'provenance.json')['sha256'],
        'baseline_audit_sha256': hashes(baseline/'audit.json')['sha256'],
        'fold_manifest_sha256': hashes(output/'fold_manifest.json')['sha256'],
        'protocol_sha256': hashes(output/'protocol.json')['sha256'],
        'frozen_package_sha256_before': hashes(FROZEN)['sha256'],
        'original_eeg_opened': False, 'cache_people_loaded': old['participants'],
        'confirmation_eeg_read': False, 'former_development_eeg_read': False,
        'board_accessed': False, 'control_enabled': False,
        'torch_version': torch.__version__, 'numpy_version': np.__version__,
        'cuda_runtime': torch.version.cuda, 'cuda_device': torch.cuda.get_device_name(0),
        'timing_scope': 'Windows RTX4060 workstation,not Z15'})
    print('LOCKED_ONE_CANDIDATE', len(folds), 'folds', len(protocol['seeds']), 'seeds', flush=True)


def load_experiment(output):
    protocol, info = read_json(output/'protocol.json'), read_json(output/'provenance.json')
    for path, digest in info['source_sha256'].items():
        if hashes(Path(path))['sha256'] != digest:
            raise ValueError('Source changed after freeze: '+path)
    if (hashes(output/'protocol.json')['sha256'] != info['protocol_sha256']
            or hashes(output/'fold_manifest.json')['sha256'] != info['fold_manifest_sha256']):
        raise ValueError('Run protocol or folds changed')
    baseline = HERE/protocol['baseline_run']
    if (hashes(baseline/'results.json')['sha256'] != protocol['baseline_results_sha256']
            or hashes(baseline/'provenance.json')['sha256'] != info['baseline_provenance_sha256']
            or hashes(baseline/'audit.json')['sha256'] != info['baseline_audit_sha256']):
        raise ValueError('Completed baseline changed')
    old, stats, waves, folds = load_run(baseline)
    if folds != read_json(output/'fold_manifest.json'):
        raise ValueError('Fold identities changed')
    return protocol, old, stats, waves, folds


def train(output):
    protocol, old, stats, waves, folds = load_experiment(output)
    configure_torch(old['compute'])
    if not torch.cuda.is_available():
        raise RuntimeError('Locked CUDA device unavailable')
    device = torch.device(old['compute']['device'])
    folder = output/'network_checkpoints'; folder.mkdir(exist_ok=True)
    for fold in folds:
        fitting, validation, target = fold_indices(stats['subjects'],stats['order'],fold)
        mean, scale = channel_scaler(waves[fitting])
        train_x = normalized_tensor(waves[fitting],mean,scale,device)
        val_x = normalized_tensor(waves[validation],mean,scale,device)
        for seed in protocol['seeds']:
            prefix = f's{fold["target"]:02d}_seed{seed}'
            prediction_path = output/'fold_predictions'/f's{fold["target"]:02d}_{protocol["candidate_method"]}_seed{seed}.npz'
            if prediction_path.exists():
                if not (folder/f'{prefix}.pt').exists() or not (folder/f'{prefix}.json').exists():
                    raise ValueError('Incomplete existing checkpoint')
                print('SKIP_COMPLETE',prefix,flush=True); continue
            if (folder/f'{prefix}.pt').exists() or (folder/f'{prefix}.json').exists():
                raise RuntimeError('Preserve interrupted artifacts for inspection: '+prefix)
            def progress(epoch,best_epoch,ba,seconds):
                print('SOURCE_VAL',prefix,'epoch',epoch,'best',best_epoch,'BA',round(ba,4),'seconds',round(seconds,1),flush=True)
            model, history = train_augmented(train_x,stats['labels'][fitting],stats['subjects'][fitting],
                                              val_x,stats['labels'][validation],stats['subjects'][validation],
                                              old['eegnet'],seed,device,progress)
            checkpoint = {'state_dict': {k:v.detach().cpu() for k,v in model.state_dict().items()},
                          'config': old['eegnet'], 'training_augmentation':protocol['augmentation'],
                          'source_mean':mean.tolist(),'source_scale':scale.tolist(),
                          'metadata':{**fold,'seed':seed,'control_enabled':False,
                                      'target_labels_used_for_selection':False}}
            torch.save(checkpoint,folder/f'{prefix}.pt'); save(folder/f'{prefix}.json',history)
            restored = torch.load(folder/f'{prefix}.pt',map_location='cpu',weights_only=True)
            model2 = EEGNetSmall(restored['config']).to(device)
            model2.load_state_dict(restored['state_dict'])
            target_x = normalized_tensor(waves[target],np.array(restored['source_mean']),np.array(restored['source_scale']),device)
            scores = network_logits(model,target_x); reloaded = network_logits(model2,target_x)
            np.testing.assert_array_equal(scores,reloaded)
            save_prediction(output,fold['target'],protocol['candidate_method'],seed,target,stats['labels'][target],
                            scores,scores.argmax(axis=1),{**fold,'seed':seed,'best_epoch':history['best_epoch'],
                            'checkpoint_reload_max_abs_error':float(np.max(np.abs(scores-reloaded)))})
            print('FOLD_COMPLETE',prefix,'epochs',history['completed_epochs'],flush=True)
            del model,model2,target_x
        del train_x,val_x


def paired_summary(candidate,reference,settings):
    if [r['subject'] for r in candidate] != [r['subject'] for r in reference]:
        raise ValueError('Paired people must match in order')
    delta = np.array([c['balanced_accuracy']-r['balanced_accuracy'] for c,r in zip(candidate,reference)])
    rng = np.random.default_rng(settings['seed'])
    boot = delta[rng.integers(0,len(delta),(settings['draws'],len(delta)))].mean(axis=1)
    return {'mean_ba_gain':float(delta.mean()),'paired_95_ci':np.quantile(boot,[.025,.975]).tolist(),
            'people_improved':int((delta>0).sum()),'people_declined':int((delta<0).sum()),
            'people_tied':int((delta==0).sum()),'per_person_gain':delta.tolist()}


def summarize(output):
    if (output/'results.json').exists():
        raise RuntimeError('Existing results preserved')
    protocol, old, stats, _, folds = load_experiment(output)
    rows, prediction_hashes, artifact_hashes, histories = [], {}, {}, []
    for fold in folds:
        _,_,target = fold_indices(stats['subjects'],stats['order'],fold)
        seed_rows = []
        for seed in protocol['seeds']:
            path = output/'fold_predictions'/f's{fold["target"]:02d}_{protocol["candidate_method"]}_seed{seed}.npz'
            with np.load(path,allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['indices'],target)
                np.testing.assert_array_equal(saved['labels'],stats['labels'][target])
                row = subject_metrics(saved['labels'],saved['predictions'],stats['subjects'][target])[0]
                row.update(seed=seed,confusion_matrix=confusion_matrix(saved['labels'],saved['predictions'],labels=[0,1]).tolist())
                seed_rows.append(row)
            prediction_hashes[path.name] = hashes(path)['sha256']
            for suffix in ('.pt','.json'):
                artifact = output/'network_checkpoints'/f's{fold["target"]:02d}_seed{seed}{suffix}'
                artifact_hashes[artifact.name] = hashes(artifact)['sha256']
            histories.append(read_json(output/'network_checkpoints'/f's{fold["target"]:02d}_seed{seed}.json'))
        rows.append({'subject':fold['target'],'trials':len(target),
                     'balanced_accuracy':float(np.mean([r['balanced_accuracy'] for r in seed_rows])),
                     'macro_f1':float(np.mean([r['macro_f1'] for r in seed_rows])),'per_seed':seed_rows})
    values = np.array([r['balanced_accuracy'] for r in rows])
    summary = {'mean_subject_balanced_accuracy':float(values.mean()),'between_subject_sd':float(values.std(ddof=1)),
               'subject_bootstrap_95_ci':bootstrap_ci(values,protocol['bootstrap']['seed']),
               'mean_subject_macro_f1':float(np.mean([r['macro_f1'] for r in rows])),'per_subject':rows,
               'seed_mean_ba':{str(seed):float(np.mean([next(s['balanced_accuracy'] for s in r['per_seed'] if s['seed']==seed) for r in rows])) for seed in protocol['seeds']}}
    baseline = read_json(HERE/protocol['baseline_run']/'results.json')['methods'][protocol['baseline_method']]
    comparison = paired_summary(rows,baseline['per_subject'],protocol['bootstrap'])
    gate = protocol['continuation_gate']
    passed = bool(values.mean()>=gate['mean_ba_at_least'] and comparison['mean_ba_gain']>=gate['paired_gain_at_least']
                  and comparison['paired_95_ci'][0]>gate['paired_ci_lower_greater_than'])
    report = {'protocol':protocol,'inherited_eegnet_config':old['eegnet'],
              'candidate':summary,'reference':baseline,'paired_comparison':comparison,
              'continuation_gate_passed':passed,'retain_unaugmented_if_failed':not passed,
              'training_cost':{'fits':len(histories),'pc_fit_seconds':sum(h['pc_fit_seconds'] for h in histories),
                               'total_epochs':sum(h['completed_epochs'] for h in histories),
                               'synthetic_rows_seen':sum(h['synthetic_rows_seen'] for h in histories)},
              'prediction_sha256':prediction_hashes,'checkpoint_sha256':artifact_hashes,
              'all_original_trials':6080,'common_scored_trials':int((stats['order']>=60).sum()),'trials_discarded':0,
              'confirmation_eeg_read':False,'former_development_eeg_read':False,'original_eeg_opened':False,
              'board_accessed':False,'control_enabled':False,'promotion_gate_passed':False,
              'frozen_package_sha256_after':hashes(FROZEN)['sha256'],'completed_at_local':datetime.now().isoformat()}
    save(output/'results.json',report)
    print(json.dumps({'candidate_ba':summary['mean_subject_balanced_accuracy'],
                      'baseline_ba':baseline['mean_subject_balanced_accuracy'],
                      'comparison':comparison,'continuation_gate_passed':passed},indent=2),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','train','summarize'))
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args = parser.parse_args()
    {'prepare':prepare,'train':train,'summarize':summarize}[args.action](args.output)

"""CPU checkpoint/normalization/validation/prediction audit; no model fitting."""
from pathlib import Path
import json

from mi_comparison_models import EEGNetSmall, mean_person_ba, normalized_tensor, network_logits, torch
import numpy as np
from sklearn.metrics import balanced_accuracy_score, f1_score, confusion_matrix
from cho2017_data import hashes
from cho2017_training_diagnostic import save
from mi_model_comparison import fold_indices, FROZEN
from mi_segmentation_experiment import load_experiment, OUTPUT, read_json, paired_summary


def audit(output):
    if (output/'audit.json').exists():
        raise RuntimeError('Existing audit preserved')
    protocol, old, stats, waves, folds = load_experiment(output)
    report = read_json(output/'results.json')
    torch.set_num_threads(4)
    maximum_error, predictions_checked = 0.0, 0
    rows = []
    for fold in folds:
        fitting,validation,target = fold_indices(stats['subjects'],stats['order'],fold)
        source = waves[fitting].astype(np.float64)
        mean = source.mean(axis=(0,2));scale = np.sqrt(((source-mean[None,:,None])**2).mean(axis=(0,2)))
        seed_metrics = []
        recorded = next(r for r in report['candidate']['per_subject'] if r['subject']==fold['target'])
        for seed in protocol['seeds']:
            prefix = f's{fold["target"]:02d}_seed{seed}'
            for suffix in ('.pt','.json'):
                path = output/'network_checkpoints'/f'{prefix}{suffix}'
                if hashes(path)['sha256']!=report['checkpoint_sha256'][path.name]:
                    raise ValueError('Checkpoint artifact changed')
            checkpoint = torch.load(output/'network_checkpoints'/f'{prefix}.pt',map_location='cpu',weights_only=True)
            np.testing.assert_array_equal(mean,checkpoint['source_mean']);np.testing.assert_array_equal(scale,checkpoint['source_scale'])
            for key,value in fold.items():
                if checkpoint['metadata'][key]!=value:raise ValueError('Checkpoint split changed')
            if checkpoint['config']!=old['eegnet'] or checkpoint['training_augmentation']!=protocol['augmentation']:
                raise ValueError('Network or augmentation configuration changed')
            model = EEGNetSmall(checkpoint['config']);model.load_state_dict(checkpoint['state_dict'])
            scores = network_logits(model,normalized_tensor(waves[target],mean,scale,'cpu'))
            path = output/'fold_predictions'/f's{fold["target"]:02d}_{protocol["candidate_method"]}_seed{seed}.npz'
            if hashes(path)['sha256']!=report['prediction_sha256'][path.name]:raise ValueError('Prediction changed')
            with np.load(path,allow_pickle=False) as stored:
                np.testing.assert_array_equal(stored['indices'],target)
                np.testing.assert_array_equal(stored['labels'],stats['labels'][target])
                np.testing.assert_allclose(scores,stored['scores'],rtol=1e-5,atol=1e-5)
                np.testing.assert_array_equal(scores.argmax(axis=1),stored['predictions'])
                if json.loads(str(stored['metadata']))['checkpoint_reload_max_abs_error']!=0:
                    raise ValueError('On-disk GPU reload not exact')
                maximum_error = max(maximum_error,float(np.max(np.abs(scores-stored['scores']))))
                ba = balanced_accuracy_score(stored['labels'],stored['predictions'])
                f1 = f1_score(stored['labels'],stored['predictions'],average='macro')
                expected = next(r for r in recorded['per_seed'] if r['seed']==seed)
                np.testing.assert_allclose([ba,f1],[expected['balanced_accuracy'],expected['macro_f1']],rtol=0,atol=1e-15)
                if confusion_matrix(stored['labels'],stored['predictions'],labels=[0,1]).tolist()!=expected['confusion_matrix']:
                    raise ValueError('Confusion matrix mismatch')
            history = read_json(output/'network_checkpoints'/f'{prefix}.json')
            best = max(history['history'],key=lambda r:r['source_validation_mean_person_ba'])
            if best['epoch']!=history['best_epoch'] or history['source_donor_people']!=fold['fit_people']:
                raise ValueError('Source-only selection/donor rule differs')
            epochs = history['completed_epochs']
            if (history['optimizer_updates']!=epochs*int(np.ceil(len(fitting)/old['eegnet']['batch_size']))
                    or history['synthetic_rows_seen']!=epochs*len(fitting) or history['real_rows_seen']!=epochs*len(fitting)):
                raise ValueError('Training budget differs')
            val_pred = network_logits(model,normalized_tensor(waves[validation],mean,scale,'cpu')).argmax(axis=1)
            val_ba = mean_person_ba(stats['labels'][validation],val_pred,stats['subjects'][validation])
            np.testing.assert_allclose(val_ba,history['source_validation_mean_person_ba'],rtol=0,atol=1e-14)
            seed_metrics.append([ba,f1]); predictions_checked += len(target)
        metrics = np.mean(seed_metrics,axis=0)
        np.testing.assert_allclose(metrics,[recorded['balanced_accuracy'],recorded['macro_f1']],rtol=0,atol=1e-15)
        rows.append({'subject':fold['target'],'balanced_accuracy':float(metrics[0])})
        print('AUDITED_PERSON',fold['target'],flush=True)
    comparison = paired_summary(rows,report['reference']['per_subject'],protocol['bootstrap'])
    if comparison!=report['paired_comparison']:raise ValueError('Paired report differs')
    mean_ba = float(np.mean([r['balanced_accuracy'] for r in rows]))
    np.testing.assert_allclose(mean_ba,report['candidate']['mean_subject_balanced_accuracy'],rtol=0,atol=1e-15)
    gate = protocol['continuation_gate']
    passed = bool(mean_ba>=gate['mean_ba_at_least'] and comparison['mean_ba_gain']>=gate['paired_gain_at_least']
                  and comparison['paired_95_ci'][0]>gate['paired_ci_lower_greater_than'])
    if passed!=report['continuation_gate_passed']:raise ValueError('Continuation decision differs')
    frozen = hashes(FROZEN)['sha256']
    if frozen!=report['frozen_package_sha256_after'] or frozen!=read_json(output/'provenance.json')['frozen_package_sha256_before']:
        raise ValueError('Frozen release changed')
    result = {'audit_passed':True,'classifier_refitted':False,'original_eeg_opened':False,
              'predictions_recomputed':predictions_checked,'gpu_cpu_max_abs_logit_error':maximum_error,
              'results_sha256':hashes(output/'results.json')['sha256'],'audit_script_sha256':hashes(Path(__file__))['sha256'],
              'confirmation_eeg_read':False,'former_development_eeg_read':False,'board_accessed':False,
              'control_enabled':False,'promotion_gate_passed':False,'frozen_package_sha256':frozen}
    save(output/'audit.json',result);print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':audit(OUTPUT)

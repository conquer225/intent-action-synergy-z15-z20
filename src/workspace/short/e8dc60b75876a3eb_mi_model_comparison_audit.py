"""Recompute saved scores/metrics without fitting or opening original EEG."""
import argparse
from datetime import datetime
import json
from pathlib import Path

from mi_comparison_models import EEGNetSmall, normalized_tensor, network_logits, mean_person_ba, torch
import numpy as np
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score

from cho2017_adaptation import alignment_reference, align_covariances
from cho2017_data import hashes
from cho2017_training_diagnostic import save
from mi_model_comparison import load_run, fold_indices, paired, FROZEN
from mi_physionet_evaluate import bootstrap_ci, subject_metrics
from mi_spatial import projected_features


def primary_reference_key(protocol):
    description = protocol['primary_reference']
    matches = [name for name in protocol['methods']
               if description == name or description.startswith(name + ' ')]
    if len(matches) != 1:
        raise ValueError('Primary reference description must identify exactly one locked method')
    return matches[0]


def summarize_saved(run):
    """Report-only repair: resolve the descriptive reference without changing the locked protocol."""
    if (run/'results.json').exists():
        raise RuntimeError('Existing results preserved')
    protocol, stats, _, folds = load_run(run)
    reference = primary_reference_key(protocol)
    manifest = json.loads((run/'trial_manifest.json').read_text(encoding='utf-8'))
    methods, prediction_hashes = {}, {}
    for method in protocol['methods']:
        rows = []
        for fold in folds:
            seeds = protocol['eegnet']['seeds'] if method == 'C2_EEGNet_SMALL' else [0]
            _, _, target = fold_indices(stats['subjects'], stats['order'], fold)
            repetitions = []
            for seed in seeds:
                path = run/'fold_predictions'/f's{fold["target"]:02d}_{method}_seed{seed}.npz'
                with np.load(path, allow_pickle=False) as prediction:
                    np.testing.assert_array_equal(prediction['indices'], target)
                    np.testing.assert_array_equal(prediction['labels'], stats['labels'][target])
                    row = subject_metrics(prediction['labels'], prediction['predictions'], stats['subjects'][target])[0]
                    row.update(seed=seed, confusion_matrix=confusion_matrix(prediction['labels'], prediction['predictions'], labels=[0,1]).tolist())
                    repetitions.append(row)
                prediction_hashes[path.name] = hashes(path)['sha256']
            rows.append({'subject': fold['target'], 'trials': len(target),
                         'balanced_accuracy': float(np.mean([r['balanced_accuracy'] for r in repetitions])),
                         'macro_f1': float(np.mean([r['macro_f1'] for r in repetitions])), 'per_seed': repetitions})
        values = np.array([row['balanced_accuracy'] for row in rows])
        methods[method] = {'mean_subject_balanced_accuracy': float(values.mean()),
                           'between_subject_sd': float(values.std(ddof=1)),
                           'subject_bootstrap_95_ci': bootstrap_ci(values, protocol['bootstrap']['seed']),
                           'mean_subject_macro_f1': float(np.mean([r['macro_f1'] for r in rows])), 'per_subject': rows}
    comparisons = {}
    gate = protocol['continuation_gate']
    for candidate in protocol['primary_candidates']:
        comparison = paired(methods[candidate]['per_subject'], methods[reference]['per_subject'], protocol['bootstrap'])
        comparison['continuation_gate_passed'] = bool(
            methods[candidate]['mean_subject_balanced_accuracy'] >= gate['mean_ba_at_least']
            and comparison['mean_ba_gain'] >= gate['paired_gain_at_least']
            and comparison['two_comparison_adjusted_97_5_ci'][0] > gate['adjusted_ci_lower_greater_than'])
        comparisons[candidate] = comparison
    passing = [name for name in comparisons if comparisons[name]['continuation_gate_passed']]
    selected = max(passing, key=lambda name: methods[name]['mean_subject_balanced_accuracy']) if passing else None
    report = {'scope': 'Training30 nested-person exploratory comparison,not independent confirmation or wearable accuracy',
              'protocol': protocol, 'primary_reference_key': reference,
              'reporting_repair': {'original_failure': 'KeyError: primary_reference contains a method description, not only its identifier',
                                  'locked_protocol_unchanged': True, 'classifier_refitted': False,
                                  'script_sha256': hashes(Path(__file__))['sha256']},
              'methods': methods, 'paired_against_fixed_B1': comparisons,
              'secondary_C1_minus_B2': paired(methods['C1_FBCSP_SELECTED']['per_subject'], methods['B2_FBCSP_LDA']['per_subject'], protocol['bootstrap']),
              'passing_candidates': passing, 'selected_for_later_confirmation': selected,
              'all_trials': len(manifest), 'author_flagged_retained': sum(r['voltage_bad'] or r['emg_bad'] for r in manifest),
              'common_scored_trials': int((stats['order'] >= 60).sum()), 'trials_discarded': 0,
              'former_development_eeg_read': False, 'confirmation_eeg_read': False, 'board_accessed': False,
              'promotion_gate_passed': False, 'control_enabled': False, 'prediction_sha256': prediction_hashes,
              'frozen_package_sha256_after': hashes(FROZEN)['sha256'], 'completed_at_local': datetime.now().isoformat()}
    save(run/'results.json', report)
    print(json.dumps({'means': {name: value['mean_subject_balanced_accuracy'] for name,value in methods.items()},
                      'passing': passing, 'selected': selected}, indent=2), flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,default=Path(__file__).resolve().parent/'output/mi_model_comparison_20261001')
    parser.add_argument('--summarize',action='store_true',help='Aggregate saved predictions with the report-only reference-name repair')
    args=parser.parse_args();run=args.run
    if args.summarize:
        summarize_saved(run)
        return
    if (run/'audit.json').exists():raise RuntimeError('Existing audit preserved')
    protocol,stats,waves,folds=load_run(run)
    report=json.loads((run/'results.json').read_text(encoding='utf-8'))
    covs,ratios=stats['covariances'],stats['log_power_ratio']
    torch.set_num_threads(4)
    differences={'classical':0.0,'gpu_to_cpu_network':0.0}
    rows_by_method={method:[] for method in protocol['methods']}
    scored_predictions=0
    checkpoint_reload_errors=[]
    for fold in folds:
        fitting,validation,target=fold_indices(stats['subjects'],stats['order'],fold)
        person=fold['target']
        for method in protocol['methods']:
            seed_rows=[]
            seeds=protocol['eegnet']['seeds'] if method=='C2_EEGNet_SMALL' else [0]
            for seed in seeds:
                path=run/'fold_predictions'/f's{person:02d}_{method}_seed{seed}.npz'
                if hashes(path)['sha256']!=report['prediction_sha256'][path.name]:raise ValueError('Prediction hash changed')
                with np.load(path,allow_pickle=False) as saved:
                    actual_labels=saved['labels'];stored_scores=saved['scores'];stored_predictions=saved['predictions']
                    np.testing.assert_array_equal(saved['indices'],target)
                np.testing.assert_array_equal(actual_labels,stats['labels'][target])
                if method=='C2_EEGNet_SMALL':
                    checkpoint=torch.load(run/'network_checkpoints'/f's{person:02d}_seed{seed}.pt',map_location='cpu',weights_only=True)
                    meta=checkpoint['metadata']
                    if meta['fit_people']!=fold['fit_people'] or meta['validation_people']!=fold['validation_people'] or meta['target']!=person:
                        raise ValueError('Checkpoint fold people changed')
                    source=waves[fitting].astype(np.float64)
                    source_mean=source.mean(axis=(0,2));source_scale=np.sqrt(((source-source_mean[None,:,None])**2).mean(axis=(0,2)))
                    np.testing.assert_array_equal(source_mean,checkpoint['source_mean'])
                    np.testing.assert_array_equal(source_scale,checkpoint['source_scale'])
                    model=EEGNetSmall(checkpoint['config'])
                    model.load_state_dict(checkpoint['state_dict'])
                    tensor=normalized_tensor(waves[target],source_mean,source_scale,'cpu')
                    scores=network_logits(model,tensor)
                    error=float(np.max(np.abs(scores-stored_scores)))
                    differences['gpu_to_cpu_network']=max(differences['gpu_to_cpu_network'],error)
                    np.testing.assert_allclose(scores,stored_scores,rtol=1e-5,atol=1e-5)
                    predicted=scores.argmax(axis=1)
                    history=json.loads((run/'network_checkpoints'/f's{person:02d}_seed{seed}.json').read_text(encoding='utf-8'))
                    best=max(history['history'],key=lambda row:row['source_validation_mean_person_ba'])
                    if best['epoch']!=history['best_epoch']:raise ValueError('Best-source-validation checkpoint rule violated')
                    val_tensor=normalized_tensor(waves[validation],source_mean,source_scale,'cpu')
                    val_pred=network_logits(model,val_tensor).argmax(axis=1)
                    val_ba=mean_person_ba(stats['labels'][validation],val_pred,stats['subjects'][validation])
                    np.testing.assert_allclose(val_ba,history['source_validation_mean_person_ba'],rtol=0,atol=1e-14)
                    with np.load(path,allow_pickle=False) as saved:
                        checkpoint_reload_errors.append(json.loads(str(saved['metadata']))['checkpoint_reload_max_abs_error'])
                    del source,model,tensor,val_tensor
                else:
                    with np.load(run/'fold_parameters'/f's{person:02d}_{method}.npz',allow_pickle=False) as fitted:
                        meta=json.loads(str(fitted['metadata']))
                        if meta['fit_people']!=fold['fit_people'] or meta['validation_people']!=fold['validation_people']:
                            raise ValueError('Classical fold metadata changed')
                        if method in ('B0_CSP_LDA','B1_EA_CSP_ERD_LDA'):
                            values=covs[target,2].copy()
                            if method=='B1_EA_CSP_ERD_LDA':
                                selected=stats['subjects']==person
                                _,whitening=alignment_reference(covs[selected,2],stats['order'][selected])
                                values=align_covariances(values,whitening)
                            features=projected_features(values[:,None],fitted['filters'])
                            if method=='B1_EA_CSP_ERD_LDA':features=np.concatenate([features,ratios[target]],axis=1)
                        else:
                            features=projected_features(covs[target][:,[0,3,4,5,6]],fitted['filters'])
                            features=features.reshape(len(target),5,2)[:,fitted['selected_positions']].reshape(len(target),-1)
                        scores=((features-fitted['mean'])/fitted['scale'])@fitted['coef']+float(fitted['intercept'])
                        np.testing.assert_allclose(scores,stored_scores,rtol=1e-10,atol=1e-10)
                        differences['classical']=max(differences['classical'],float(np.max(np.abs(scores-stored_scores))))
                        predicted=(scores>0).astype(int)
                np.testing.assert_array_equal(predicted,stored_predictions)
                ba=float(balanced_accuracy_score(actual_labels,predicted));f1=float(f1_score(actual_labels,predicted,average='macro'))
                matrix=confusion_matrix(actual_labels,predicted,labels=[0,1]).tolist()
                recorded=next(r for r in report['methods'][method]['per_subject'] if r['subject']==person)
                seed_record=next(r for r in recorded['per_seed'] if r['seed']==seed)
                if matrix!=seed_record['confusion_matrix']:raise ValueError('Confusion matrix differs')
                np.testing.assert_allclose([ba,f1],[seed_record['balanced_accuracy'],seed_record['macro_f1']],rtol=0,atol=1e-15)
                seed_rows.append((ba,f1));scored_predictions+=len(target)
            rows_by_method[method].append(np.mean(seed_rows,axis=0).tolist())
        print('AUDITED_PERSON',person,flush=True)
    for method,rows in rows_by_method.items():
        values=np.array(rows);summary=report['methods'][method]
        np.testing.assert_allclose(values.mean(axis=0),[summary['mean_subject_balanced_accuracy'],summary['mean_subject_macro_f1']],rtol=0,atol=1e-14)
    for candidate in protocol['primary_candidates']:
        delta=np.array(rows_by_method[candidate])[:,0]-np.array(rows_by_method[primary_reference_key(protocol)])[:,0]
        rng=np.random.default_rng(protocol['bootstrap']['seed'])
        boot=delta[rng.integers(0,len(delta),size=(10000,len(delta)))].mean(axis=1)
        comparison=report['paired_against_fixed_B1'][candidate]
        ci=np.quantile(boot,[.0125,.9875])
        np.testing.assert_allclose(ci,comparison['two_comparison_adjusted_97_5_ci'],rtol=0,atol=1e-14)
        gate=protocol['continuation_gate']
        passed=bool(np.array(rows_by_method[candidate])[:,0].mean()>=gate['mean_ba_at_least'] and delta.mean()>=gate['paired_gain_at_least'] and ci[0]>0)
        if passed!=comparison['continuation_gate_passed']:raise ValueError('Continuation gate differs')
    frozen_hash=hashes(Path('D:/ican/handoff/GuardianLoop_FROZEN_20261001.zip'))['sha256']
    provenance=json.loads((run/'provenance.json').read_text(encoding='utf-8'))
    if frozen_hash!=provenance['frozen_package_sha256_before'] or frozen_hash!=report['frozen_package_sha256_after']:
        raise ValueError('Frozen release package changed')
    result={'audit_passed':True,'classifier_refitted':False,'original_eeg_opened':False,'board_accessed':False,
            'scored_predictions_recomputed':scored_predictions,'max_abs_score_errors':differences,
            'network_on_disk_reload_max_abs_error':max(checkpoint_reload_errors),
            'frozen_package_sha256':frozen_hash,'results_sha256':hashes(run/'results.json')['sha256'],
            'audit_script_sha256':hashes(Path(__file__))['sha256'],'promotion_gate_passed':False,'control_enabled':False}
    save(run/'audit.json',result);print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()

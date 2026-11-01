"""Independent scaler, selection and saved-prediction audit; never refit."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time

from mi_rms_comparison import (load, save, digest, torch, EEGNetSmall, channel_scaler,
                               normalized_tensor, network_logits, shared_window_rms,
                               fold_indices, metric_rows, aggregate, TRANSFORM_ID, np)


def audit(output):
    if (output/'audit.json').exists():
        raise RuntimeError('Previous audit preserved')
    p,baseline,stats,waves,folds=load(output)
    report=json.loads((output/'results.json').read_text(encoding='utf-8'))
    freeze=json.loads((output/'checkpoint_freeze.json').read_text(encoding='utf-8'))
    for name,expected in freeze['checkpoint_sha256'].items():
        if digest(output/'network_checkpoints'/name)!=expected: raise ValueError('Frozen checkpoint changed')
    for name,expected in report['candidate_prediction_sha256'].items():
        if digest(output/'fold_predictions'/name)!=expected: raise ValueError('Saved prediction changed')
    torch.set_num_threads(4)
    normalized=shared_window_rms(waves)
    all_rows=[]
    max_cpu_error=0
    started=time.monotonic()
    checked=0
    for fold in folds:
        fitting,_,target=fold_indices(stats['subjects'],stats['order'],fold)
        mean,scale=channel_scaler(normalized[fitting])
        row={'subject':fold['target'],'windows':len(target),'baseline':{},'shared_rms':{}}
        for seed in baseline['eegnet']['seeds']:
            prefix=f's{fold["target"]:02d}_seed{seed}'
            cp=torch.load(output/'network_checkpoints'/(prefix+'.pt'),map_location='cpu',weights_only=True)
            if cp['metadata']!={**fold,'seed':seed,'input_transform':TRANSFORM_ID,
                    'target_labels_used_for_selection':False,'promotion_gate_passed':False,'control_enabled':False}:
                raise ValueError('Candidate metadata changed')
            np.testing.assert_array_equal(cp['source_mean'],mean)
            np.testing.assert_array_equal(cp['source_scale'],scale)
            history=json.loads((output/'network_checkpoints'/(prefix+'.json')).read_text(encoding='utf-8'))
            validation=np.array([item['source_validation_mean_person_ba'] for item in history['history']])
            if (history['best_epoch']!=int(validation.argmax())+1
                    or history['source_validation_mean_person_ba']!=float(validation.max())
                    or history['completed_epochs']!=len(validation)):
                raise ValueError('Earliest source-validation optimum not used')
            if (history['completed_epochs']<baseline['eegnet']['epochs_max']
                    and history['completed_epochs']-history['best_epoch']!=baseline['eegnet']['early_stop_patience']):
                raise ValueError('Locked source early-stop budget changed')
            model=EEGNetSmall(cp['config'])
            model.load_state_dict(cp['state_dict'])
            cpu_scores=network_logits(model,normalized_tensor(normalized[target],mean,scale,'cpu'))
            for method in ('baseline','shared_rms'):
                with np.load(output/'fold_predictions'/(prefix+'_'+method+'.npz'),allow_pickle=False) as data:
                    np.testing.assert_array_equal(data['indices'],target)
                    np.testing.assert_array_equal(data['labels'],stats['labels'][target])
                    np.testing.assert_array_equal(data['amplitude_factors'],p['stress_amplitude_factors'])
                    np.testing.assert_array_equal(data['predictions'],data['scores'].argmax(2))
                    scores=data['scores'].copy()
                if method=='shared_rms':
                    np.testing.assert_allclose(cpu_scores,scores[0],rtol=0,atol=p['numerical_atol'])
                    np.testing.assert_array_equal(cpu_scores.argmax(1),scores[0].argmax(1))
                    max_cpu_error=max(max_cpu_error,float(np.max(np.abs(cpu_scores-scores[0]))))
                row[method][str(seed)]=[{'amplitude_factor':factor,
                    **metric_rows(stats['labels'][target],score),
                    'agreement_with_clean':float(np.mean(score.argmax(1)==scores[0].argmax(1)))}
                    for factor,score in zip(p['stress_amplitude_factors'],scores)]
            checked+=1
        all_rows.append(row)
        print('AUDIT_PERSON',fold['target'],flush=True)
    recomputed,comparison=aggregate(all_rows,baseline['eegnet']['seeds'],p['stress_amplitude_factors'],p['bootstrap'])
    if recomputed!=report['methods'] or comparison!=report['paired_clean_comparison']:
        raise ValueError('Report cannot be reproduced from saved predictions')
    dominance={}
    for method,conditions in recomputed.items():
        dominance[method]=[]
        for condition in conditions:
            rates=np.array([person['per_seed'][str(seed)]['left_fraction']
                for person in condition['per_person'] for seed in baseline['eegnet']['seeds']])
            dominance[method].append({'amplitude_factor':condition['amplitude_factor'],
                'person_seed_models':len(rates),'one_class_only_count':int(np.sum((rates==0)|(rates==1))),
                'mean_dominant_class_fraction':float(np.maximum(rates,1-rates).mean()),
                'scope':'Descriptive model count, not independent statistical samples'})
    checks={'models_audited':checked,'scaler_and_scope_checks_exact':True,
        'source_selection_checks_exact':True,'all_report_metrics_recomputed':True,
        'clean_gpu_cpu_classes_exact':True,'clean_gpu_cpu_logit_max_error':max_cpu_error,
        'scored_windows_per_seed':int(np.sum(stats['order']>=60)),
        'script_sha256':digest(Path(__file__)),'elapsed_s':time.monotonic()-started,
        'completed_at':datetime.now().astimezone().isoformat(),
        'model_refitted':False,'board_accessed':False,'promotion_gate_passed':False,
        'descriptive_class_dominance':dominance}
    save(output/'audit.json',checks)
    print(json.dumps(checks),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'output/mi_rms_comparison_20261003')
    audit(parser.parse_args().output.resolve())

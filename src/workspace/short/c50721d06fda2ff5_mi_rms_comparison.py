"""Frozen-fold shared-RMS retraining, then separate outer-person evaluation."""
import argparse
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time

from mi_comparison_models import (torch, EEGNetSmall, channel_scaler, configure_torch,
                                  normalized_tensor, train_network, network_logits)
import numpy as np
import scipy
from sklearn.metrics import balanced_accuracy_score, f1_score, confusion_matrix
from threadpoolctl import threadpool_limits

from mi_model_comparison import load_run, fold_indices
from mi_live_scale_diagnostic import digest, read_json
from mi_window_rms import TRANSFORM_ID, shared_window_rms

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / 'output/mi_rms_runtime_20261003'
PROTOCOL = HERE / 'mi_rms_comparison_protocol.json'


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def load(output):
    lock = read_json(output/'lock.json')
    for name, expected in lock['source_sha256'].items():
        if digest(Path(name)) != expected:
            raise ValueError('Locked source changed: ' + name)
    p = read_json(output/'protocol.json')
    if digest(output/'protocol.json') != lock['protocol_sha256']:
        raise ValueError('Protocol changed after locking')
    baseline, stats, waves, folds = load_run(HERE/p['source_run'])
    if (p['source_people'] != baseline['participants']
            or p['channels'] != baseline['channels']
            or p['transform_id'] != TRANSFORM_ID
            or set(stats['subjects']) & set(p['forbidden_confirmation_people'])):
        raise ValueError('Fixed montage or training-only source scope changed')
    for name, expected in lock['baseline_artifact_sha256'].items():
        if digest(Path(name)) != expected:
            raise ValueError('Baseline artifact changed: ' + name)
    return p, baseline, stats, waves, folds


def prepare(output):
    if output.exists():
        raise RuntimeError('Existing run preserved; choose a fresh directory')
    p = read_json(PROTOCOL)
    baseline, stats, waves, folds = load_run(HERE/p['source_run'])
    if (p['source_people'] != baseline['participants'] or p['channels'] != baseline['channels']
            or baseline['eegnet']['seeds'] != [42,43,44]):
        raise ValueError('The comparison must reuse all frozen people and seeds')
    configure_torch(baseline['compute'])
    if not torch.cuda.is_available():
        raise RuntimeError('Locked CUDA device unavailable')
    result = read_json(HERE/p['source_run']/'results.json')
    artifacts = {}
    for fold in folds:
        for seed in baseline['eegnet']['seeds']:
            prefix=f's{fold["target"]:02d}_seed{seed}'
            checkpoint=HERE/p['source_run']/'network_checkpoints'/(prefix+'.pt')
            prediction=HERE/p['source_run']/'fold_predictions'/f's{fold["target"]:02d}_C2_EEGNet_SMALL_seed{seed}.npz'
            actual = digest(prediction)
            if actual != result['prediction_sha256'][prediction.name]:
                raise ValueError('Baseline prediction no longer matches its report')
            artifacts[str(checkpoint)] = digest(checkpoint)
            artifacts[str(prediction)] = actual
    sources=[Path(__file__),PROTOCOL,HERE/'test_mi_window_rms.py',
             HERE.parent/'pynq_guardianloop/mi_window_rms.py',
             RUNTIME/'mi_eegnet_portable.py',RUNTIME/'mi_window_rms.py']
    output.mkdir(parents=True)
    snapshot=output/'code_snapshot'
    snapshot.mkdir()
    for path in sources:
        name=('rms_runtime_' + path.name) if path.parent==RUNTIME else path.name
        shutil.copy2(path,snapshot/name)
    shutil.copy2(PROTOCOL,output/'protocol.json')
    save(output/'lock.json',{'started_at':datetime.now().astimezone().isoformat(),
        'source_sha256':{str(path):digest(path) for path in sources},
        'protocol_sha256':digest(output/'protocol.json'),
        'fold_manifest_sha256':digest(HERE/p['source_run']/'fold_manifest.json'),
        'baseline_artifact_sha256':artifacts,
        'source_cache_sha256':read_json(HERE/p['source_run']/'provenance.json')['cache_sha256'],
        'software':{'torch':torch.__version__,'numpy':np.__version__,'scipy':scipy.__version__,'python':sys.version},
        'cuda_device':torch.cuda.get_device_name(0),'candidate_windows':len(waves),
        'outer_target_scores_opened':False,'board_accessed':False})
    print('PREPARED',output,'folds',len(folds),'candidate_models',len(folds)*3,flush=True)


def train(output):
    if (output/'checkpoint_freeze.json').exists():
        raise RuntimeError('All checkpoints frozen; do not retrain after outer scoring')
    p, baseline, stats, waves, folds=load(output)
    configure_torch(baseline['compute'])
    device=torch.device(baseline['compute']['device'])
    normalized=shared_window_rms(waves)
    folder=output/'network_checkpoints'
    folder.mkdir(exist_ok=True)
    started=time.monotonic()
    completed=0
    for fold in folds:
        fitting,validation,_=fold_indices(stats['subjects'],stats['order'],fold)
        mean,scale=channel_scaler(normalized[fitting])
        train_x=normalized_tensor(normalized[fitting],mean,scale,device)
        validation_x=normalized_tensor(normalized[validation],mean,scale,device)
        for seed in baseline['eegnet']['seeds']:
            prefix=f's{fold["target"]:02d}_seed{seed}'
            checkpoint=folder/(prefix+'.pt')
            history_path=folder/(prefix+'.json')
            if checkpoint.exists() or history_path.exists():
                if not (checkpoint.exists() and history_path.exists()):
                    raise RuntimeError('Partial checkpoint preserved: ' + prefix)
                restored=torch.load(checkpoint,map_location='cpu',weights_only=True)
                if restored['metadata'] != {**fold,'seed':seed,'input_transform':TRANSFORM_ID,
                        'target_labels_used_for_selection':False,'promotion_gate_passed':False,'control_enabled':False}:
                    raise ValueError('Resumed checkpoint scope changed')
                completed+=1
                print('SKIP_COMPLETE',prefix,flush=True)
                continue
            def progress(epoch,best_epoch,ba,seconds):
                print('SOURCE_ONLY',prefix,'epoch',epoch,'best',best_epoch,'BA',round(ba,4),
                      'seconds',round(seconds,1),flush=True)
            model,history=train_network(train_x,stats['labels'][fitting],validation_x,
                stats['labels'][validation],stats['subjects'][validation],baseline['eegnet'],seed,device,progress)
            values={'state_dict':{key:value.detach().cpu() for key,value in model.state_dict().items()},
                'config':baseline['eegnet'],'source_mean':mean.tolist(),'source_scale':scale.tolist(),
                'metadata':{**fold,'seed':seed,'input_transform':TRANSFORM_ID,
                    'target_labels_used_for_selection':False,'promotion_gate_passed':False,'control_enabled':False}}
            temporary=checkpoint.with_suffix('.pt.partial')
            if temporary.exists():
                raise RuntimeError('Previous incomplete generated checkpoint preserved')
            torch.save(values,temporary)
            temporary.rename(checkpoint)
            save(history_path,history)
            completed+=1
            print('TRAIN_COMPLETE',completed,'/90',prefix,'epochs',history['completed_epochs'],
                  'total_seconds',round(time.monotonic()-started,1),flush=True)
            del model
        del train_x,validation_x
    hashes={path.name:digest(path) for path in sorted(folder.iterdir())}
    if len(hashes)!=180:
        raise ValueError('Exactly90 checkpoints and90 source-only histories required')
    save(output/'checkpoint_freeze.json',{'frozen_at':datetime.now().astimezone().isoformat(),
        'checkpoint_sha256':hashes,'models':completed,'outer_target_scores_opened':False,
        'training_elapsed_s':time.monotonic()-started})
    print('ALL90_FROZEN',flush=True)


def metric_rows(labels,scores):
    prediction=scores.argmax(axis=1)
    return {'balanced_accuracy':float(balanced_accuracy_score(labels,prediction)),
        'macro_f1':float(f1_score(labels,prediction,average='macro',zero_division=0)),
        'left_fraction':float(np.mean(prediction==0)),
        'confusion_matrix':confusion_matrix(labels,prediction,labels=[0,1]).tolist()}


def aggregate(rows,seeds,factors,bootstrap):
    result={}
    rng=np.random.default_rng(bootstrap['seed'])
    for method in ('baseline','shared_rms'):
        conditions=[]
        for index,factor in enumerate(factors):
            people=[]
            for row in rows:
                reps=[row[method][str(seed)][index] for seed in seeds]
                people.append({'subject':row['subject'],'windows':row['windows'],
                    **{key:float(np.mean([rep[key] for rep in reps])) for key in
                       ('balanced_accuracy','macro_f1','left_fraction','agreement_with_clean')},
                    'per_seed':{str(seed):row[method][str(seed)][index] for seed in seeds}})
            values=np.array([row['balanced_accuracy'] for row in people])
            boot=values[rng.integers(0,len(values),size=(bootstrap['draws'],len(values)))].mean(axis=1)
            seed_means=[float(np.mean([row['per_seed'][str(seed)]['balanced_accuracy'] for row in people])) for seed in seeds]
            conditions.append({'amplitude_factor':factor,'mean_person_ba':float(values.mean()),
                'person_ba_sd':float(values.std(ddof=1)),'person_bootstrap95':np.quantile(boot,[.025,.975]).tolist(),
                'mean_person_macro_f1':float(np.mean([row['macro_f1'] for row in people])),
                'mean_person_left_fraction':float(np.mean([row['left_fraction'] for row in people])),
                'mean_person_agreement_with_clean':float(np.mean([row['agreement_with_clean'] for row in people])),
                'seed_mean_ba':dict(zip(map(str,seeds),seed_means)),
                'between_seed_mean_sd':float(np.std(seed_means,ddof=1)),'per_person':people})
        result[method]=conditions
    differences=np.array([c['balanced_accuracy']-b['balanced_accuracy'] for c,b in
        zip(result['shared_rms'][0]['per_person'],result['baseline'][0]['per_person'])])
    rng=np.random.default_rng(bootstrap['seed'])
    boot=differences[rng.integers(0,len(differences),size=(bootstrap['draws'],len(differences)))].mean(axis=1)
    return result,{'mean_ba_gain':float(differences.mean()),'paired_person95_ci':np.quantile(boot,[.025,.975]).tolist(),
        'people_improved':int(np.sum(differences>0)),'people_declined':int(np.sum(differences<0)),
        'people_tied':int(np.sum(differences==0)),'per_person_differences':differences.tolist()}


def portable_checks(output,p,checkpoint,stats,waves):
    metadata={'status':'offline_shared_rms_only','input_transform':TRANSFORM_ID,
        'channels':p['channels'],'window_samples':500,'sample_rate_hz':250,'control_enabled':False,
        'production_eligible':False,'promotion_gate_passed':False,'config':checkpoint['config'],
        'source_metadata':checkpoint['metadata'],'arm_runtime_verified':False,
        'source_preprocessing':'Fixed8 CAR/notch/1-45/8-30 -> shared complete-window RMS -> frozen source scaler'}
    tensors={key:value.numpy() for key,value in checkpoint['state_dict'].items() if not key.endswith('.num_batches_tracked')}
    artifact=output/'experimental_rms_eegnet.npz'
    if artifact.exists(): raise RuntimeError('Previous candidate export preserved')
    np.savez(artifact,**tensors,source_mean=checkpoint['source_mean'],source_scale=checkpoint['source_scale'],metadata=json.dumps(metadata))
    specification=importlib.util.spec_from_file_location('isolated_rms_portable',RUNTIME/'mi_eegnet_portable.py')
    module=importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    portable=module.OfflineEEGNet(artifact,allow_experimental=True)
    from mi_eegnet_portable import OfflineEEGNet
    try:
        OfflineEEGNet(artifact,allow_experimental=True)
    except ValueError:
        old_loader_refused=True
    else:
        raise ValueError('Old runtime must reject a differently preprocessed artifact')
    reference=EEGNetSmall(checkpoint['config'])
    reference.load_state_dict(checkpoint['state_dict'])
    reference.eval()
    # No outer target or real cue labels are used to choose these probes.
    indices=np.flatnonzero(np.isin(stats['subjects'],checkpoint['metadata']['fit_people']))[:256]
    expected=network_logits(reference,normalized_tensor(shared_window_rms(waves[indices]),
        np.asarray(checkpoint['source_mean']),np.asarray(checkpoint['source_scale']),'cpu'))
    with threadpool_limits(limits=1):
        actual=np.concatenate([portable.logits(waves[indices[start:start+16]]) for start in range(0,len(indices),16)])
    error=float(np.max(np.abs(actual-expected)))
    if error>p['numerical_atol'] or not np.array_equal(actual.argmax(1),expected.argmax(1)):
        raise ValueError('Shared-RMS portable numerical parity failed')
    live=[]
    capture=HERE/'output/mi_live_capture_20261003/full_capture_audit'
    audit=read_json(capture/'AUDIT.json')
    with threadpool_limits(limits=1):
        for path in sorted(capture.glob('*.npz')):
            if digest(path)!=audit['file_sha256'][path.name]: raise ValueError('Live waveform changed')
            with np.load(path,allow_pickle=False) as data: waveform=data['filtered_uv'].copy()
            gain_scores=np.stack([portable.logits(waveform*factor)[0] for factor in p['stress_amplitude_factors']])
            live.append({'trial_id':path.stem,'amplitude_factors':p['stress_amplitude_factors'],
                'logits':gain_scores.tolist(),'outputs':['left','right'][int(gain_scores[0].argmax())],
                'gain_logit_max_error':float(np.max(np.abs(gain_scores-gain_scores[:1]))),
                'gain_classes_equal':bool(np.all(gain_scores.argmax(1)==gain_scores[0].argmax()))})
    return {'artifact_sha256':digest(artifact),'fixed_choice':p['runtime_choice'],
        'source_probe_windows':len(indices),'torch_numpy_max_logit_error':error,
        'classes_exact':True,'old_loader_refused':old_loader_refused,'real_probe_windows':live,
        'real_cue_labels_used':False,'real_accuracy_scored':False,'arm_executed':False,'board_changed':False}


def evaluate(output):
    if (output/'results.json').exists(): raise RuntimeError('Completed outer scores preserved')
    p,baseline,stats,waves,folds=load(output)
    freeze=read_json(output/'checkpoint_freeze.json')
    for name,expected in freeze['checkpoint_sha256'].items():
        if digest(output/'network_checkpoints'/name)!=expected: raise ValueError('Frozen checkpoint changed')
    configure_torch(baseline['compute'])
    device=baseline['compute']['device']
    seeds=baseline['eegnet']['seeds']
    factors=p['stress_amplitude_factors']
    rows=[]
    predictions=output/'fold_predictions'
    predictions.mkdir(exist_ok=True)
    started=time.monotonic()
    baseline_parity_max=0
    for fold in folds:
        _,_,target=fold_indices(stats['subjects'],stats['order'],fold)
        row={'subject':fold['target'],'windows':len(target),'baseline':{},'shared_rms':{}}
        for method in ('baseline','shared_rms'):
            for seed in seeds:
                prefix=f's{fold["target"]:02d}_seed{seed}'
                path=(HERE/p['source_run'] if method=='baseline' else output)/'network_checkpoints'/(prefix+'.pt')
                cp=torch.load(path,map_location='cpu',weights_only=True)
                if any(cp['metadata'][key]!=fold[key] for key in ('target','fit_people','validation_people')):
                    raise ValueError('Checkpoint and outer fold disagree')
                model=EEGNetSmall(cp['config']).to(device)
                model.load_state_dict(cp['state_dict'])
                scores=[]
                for factor in factors:
                    values=waves[target]*factor
                    if method=='shared_rms': values=shared_window_rms(values)
                    x=normalized_tensor(values,np.asarray(cp['source_mean']),np.asarray(cp['source_scale']),device)
                    scores.append(network_logits(model,x))
                scores=np.stack(scores)
                if method=='baseline':
                    gold=HERE/p['source_run']/'fold_predictions'/f's{fold["target"]:02d}_C2_EEGNet_SMALL_seed{seed}.npz'
                    with np.load(gold,allow_pickle=False) as saved:
                        np.testing.assert_array_equal(saved['indices'],target)
                        np.testing.assert_array_equal(saved['labels'],stats['labels'][target])
                        np.testing.assert_allclose(scores[0],saved['scores'],rtol=0,atol=p['numerical_atol'])
                        np.testing.assert_array_equal(scores[0].argmax(1),saved['predictions'])
                        baseline_parity_max=max(baseline_parity_max,float(np.max(np.abs(scores[0]-saved['scores']))))
                condition_rows=[]
                for factor,score in zip(factors,scores):
                    condition_rows.append({'amplitude_factor':factor,**metric_rows(stats['labels'][target],score),
                        'agreement_with_clean':float(np.mean(score.argmax(1)==scores[0].argmax(1)))})
                row[method][str(seed)]=condition_rows
                file=predictions/(prefix+'_'+method+'.npz')
                np.savez_compressed(file,indices=target,labels=stats['labels'][target],
                    amplitude_factors=factors,scores=scores,predictions=scores.argmax(2))
                del model,x
        rows.append(row)
        print('EVALUATED',fold['target'],'/',len(rows),'of30',flush=True)
    methods,comparison=aggregate(rows,seeds,factors,p['bootstrap'])
    gate=p['continuation_gate']
    passed=bool(methods['shared_rms'][0]['mean_person_ba']>=gate['candidate_mean_ba_min']
        and comparison['mean_ba_gain']>=gate['paired_mean_gain_min']
        and comparison['paired_person95_ci'][0]>gate['paired95_lower_greater_than']
        and all(row['mean_person_agreement_with_clean']>=gate['compression_label_agreement_min']
                for row in methods['shared_rms'][1:]))
    choice=p['runtime_choice']
    checkpoint=torch.load(output/'network_checkpoints'/f's{choice["target"]:02d}_seed{choice["seed"]}.pt',
                          map_location='cpu',weights_only=True)
    checks=portable_checks(output,p,checkpoint,stats,waves)
    report={'scope':'Original30 development-person nested LOSO; not independent confirmation or true Cyton accuracy',
        'protocol':p,'methods':methods,'paired_clean_comparison':comparison,'continuation_gate_passed':passed,
        'exploratory_clean_improvement_supported':bool(comparison['paired_person95_ci'][0]>0),
        'baseline_reproduction_max_logit_error':baseline_parity_max,'portable_checks':checks,
        'candidate_checkpoints':90,'scored_windows_per_seed':sum(row['windows'] for row in rows),
        'candidate_prediction_sha256':{path.name:digest(path) for path in sorted(predictions.iterdir())},
        'completed_at':datetime.now().astimezone().isoformat(),'evaluation_elapsed_s':time.monotonic()-started,
        'independent_confirmation_people_read':False,'board_accessed':False,'board_model_changed':False,
        'pl_changed':False,'promotion_gate_passed':False,'physical_control_enabled':False}
    save(output/'results.json',report)
    print(json.dumps({'means':{m:[c['mean_person_ba'] for c in values] for m,values in methods.items()},
        'paired':comparison,'continuation_gate_passed':passed,'portable_error':checks['torch_numpy_max_logit_error']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','train','evaluate'))
    parser.add_argument('--output',type=Path,default=HERE/'output/mi_rms_comparison_20261003')
    args=parser.parse_args()
    {'prepare':prepare,'train':train,'evaluate':evaluate}[args.action](args.output.resolve())

"""Fixed-montage five-cue development baseline; no deployment or actuator access."""
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
import torch
from torch import nn

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy import signal
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score
from sklearn.preprocessing import StandardScaler

from mi_comparison_models import EEGNetSmall, channel_scaler, configure_torch, network_logits, normalized_tensor
from mi_finger_data import HERE, RUN, ROOT, FIXED, header, read_signals, sha256_file, write_json


def split_people(protocol, target):
    source = [p for p in protocol['development_people'] if p!=target]
    source.sort(key=lambda p: hashlib.sha256(f'finger-fold-20261001:{target}:{p}'.encode()).digest())
    return sorted(source[3:]), sorted(source[:3])


def build_cache(protocol, audit):
    path = RUN/'development_trials.npz'
    if path.exists():
        integrity = json.loads((RUN/'extraction_audit.json').read_text(encoding='utf-8'))
        if sha256_file(path)!=integrity['cache_sha256'] or sha256_file(RUN/'protocol.json')!=integrity['protocol_sha256']:
            raise ValueError('Cache/protocol checksum mismatch')
        return path
    waves, features, precue, labels, people, indexes, run_numbers, trial_ids = [],[],[],[],[],[],[],[]
    amplitude = []
    notch = signal.tf2sos(*signal.iirnotch(50,30,fs=512))
    broad_sos = np.vstack([notch,signal.butter(4,[1,40],btype='bandpass',fs=512,output='sos')])
    neural_sos = signal.butter(4,[8,30],btype='bandpass',fs=512,output='sos')
    band_sos = [signal.butter(4,band,btype='bandpass',fs=512,output='sos') for band in protocol['bands']]
    records = [r for r in audit['records'] if r['person'] in protocol['development_people'] and r['task']=='random']
    if len(records)!=32: raise ValueError('Exactly32 development random runs required')
    for record in records:
        edf_path = ROOT/(record['stem']+'_eeg.edf'); info = header(edf_path)
        raw,digital = read_signals(edf_path,info,FIXED)
        broad = signal.sosfilt(broad_sos,raw,axis=1)
        neural = signal.sosfilt(neural_sos,broad,axis=1)
        bands = np.stack([signal.sosfilt(sos,broad,axis=1) for sos in band_sos])
        cues = [r for r in record['intervals'] if 3<=r['code']<=7]
        for index,cue in enumerate(cues):
            onset = cue['start_sample']
            def piece(seconds):
                a,b = [onset+round(s*512) for s in seconds]
                if a<0 or b>raw.shape[1] or b-a!=1024: raise ValueError('Incomplete2s window')
                return slice(a,b)
            task = piece(protocol['window_seconds']); baseline = piece(protocol['baseline_seconds'])
            before = piece(protocol['precue_control_seconds'])
            power = np.var(bands[:,:,task],axis=2)
            base = np.var(bands[:,:,baseline],axis=2)
            control = np.var(bands[:,:,before],axis=2)
            if min(power.min(),base.min(),control.min())<=1e-12: raise ValueError('Degenerate band variance; no silent floor')
            log_base = np.log(base)
            features.append(np.stack([np.log(power),np.log(power)-log_base]))
            precue.append(np.stack([np.log(control),np.log(control)-log_base]))
            waveform = signal.resample_poly(neural[:,task],125,256,axis=1,window=('kaiser',5.0),padtype='constant')
            if waveform.shape!=(8,500): raise ValueError('Antialias resampling shape mismatch')
            waves.append(waveform.astype(np.float32))
            labels.append(cue['code']-3); people.append(record['person']); indexes.append(index)
            run_number = int(record['stem'].split('_run-')[-1]); run_numbers.append(run_number)
            trial_ids.append(f'{record["stem"]}:cue{index:03d}')
        amplitude.append(dict(stem=record['stem'], raw_max_abs_uV=float(abs(raw).max()),
                              raw_rms_uV=np.sqrt(np.mean(raw**2,axis=1)).tolist(),
                              digital_rail_fraction=np.mean((digital==-32768)|(digital==32767),axis=1).tolist(),
                              trials=len(cues), no_trials_rejected=True))
        print('EXTRACTED '+record['stem']+f' {len(cues)} cues',flush=True)
    np.savez_compressed(path,waveforms=np.stack(waves),features=np.stack(features),precue=np.stack(precue),
                        labels=np.array(labels),people=np.array(people),trial_index=np.array(indexes),
                        run_number=np.array(run_numbers),trial_id=np.array(trial_ids))
    write_json(RUN/'extraction_audit.json',dict(cache_sha256=sha256_file(path),protocol_sha256=sha256_file(RUN/'protocol.json'),
        data_audit_sha256=sha256_file(RUN/'data_audit.json'), channels=FIXED, amplitude=amplitude,
        trial_count=len(labels), development_people=protocol['development_people'],
        confirmation_people_waveforms_not_read=protocol['confirmation_people'], reference='linked mastoids, unchanged',
        board_accessed=False, control_enabled=False))
    return path


class FingerEEGNet(EEGNetSmall):
    def __init__(self, config):
        super().__init__(config)
        self.dense = nn.Linear(self.dense.in_features,5)
        nn.init.xavier_uniform_(self.dense.weight); nn.init.zeros_(self.dense.bias)


def metrics(labels,prediction):
    if set(labels)!={0,1,2,3,4}: raise ValueError('All five classes required')
    return dict(balanced_accuracy=float(balanced_accuracy_score(labels,prediction)),
                macro_f1=float(f1_score(labels,prediction,labels=range(5),average='macro',zero_division=0)),
                confusion_matrix=confusion_matrix(labels,prediction,labels=range(5)).tolist(),
                class_counts=np.bincount(labels,minlength=5).tolist(), trial_count=len(labels),coverage=1.0)


def person_ba(labels,predictions,people):
    return float(np.mean([balanced_accuracy_score(labels[people==p],predictions[people==p]) for p in np.unique(people)]))


def train_network(train_x,train_y,val_x,val_y,val_people,config,seed,device):
    torch.manual_seed(seed); np.random.seed(seed)
    model = FingerEEGNet(config).to(device)
    train_labels = torch.as_tensor(train_y,dtype=torch.long,device=device)
    optimizer = torch.optim.Adam(model.parameters(),lr=config['learning_rate'],betas=tuple(config['betas']),weight_decay=config['weight_decay'])
    best, best_epoch, state = -1.,0,None
    history=[]; started=time.monotonic()
    for epoch in range(1,config['epochs_max']+1):
        model.train(); order=torch.randperm(len(train_x),device=device)
        for i in range(0,len(order),config['batch_size']):
            selected=order[i:i+config['batch_size']]
            optimizer.zero_grad(set_to_none=True)
            loss=nn.functional.cross_entropy(model(train_x[selected]),train_labels[selected])
            if not torch.isfinite(loss): raise ValueError('Nonfinite loss')
            loss.backward(); optimizer.step(); model.constrain()
        score=person_ba(val_y,network_logits(model,val_x).argmax(axis=1),val_people)
        history.append(dict(epoch=epoch, source_validation_mean_person_ba=score))
        if score>best:
            best,best_epoch=score,epoch
            state={key:value.detach().clone() for key,value in model.state_dict().items()}
        if epoch-best_epoch>=config['early_stop_patience']: break
    model.load_state_dict(state); model.eval()
    return model,dict(seed=seed,best_epoch=best_epoch,completed_epochs=epoch,history=history,
                      source_validation_mean_person_ba=best,pc_fit_seconds=time.monotonic()-started,
                      parameter_count=sum(p.numel() for p in model.parameters()))


def fit_lda(train_x,labels,target_x):
    scaler=StandardScaler().fit(train_x)
    model=LinearDiscriminantAnalysis(solver='lsqr',shrinkage='auto').fit(scaler.transform(train_x),labels)
    started=time.perf_counter(); predicted=model.predict(scaler.transform(target_x)); elapsed=time.perf_counter()-started
    return predicted,elapsed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract-only',action='store_true')
    args=parser.parse_args()
    protocol=json.loads((RUN/'protocol.json').read_text(encoding='utf-8'))
    audit=json.loads((RUN/'data_audit.json').read_text(encoding='utf-8'))
    if audit['duplicate_edf_files']: raise ValueError('Duplicate EEG recordings need resolution before training')
    path=build_cache(protocol,audit)
    if args.extract_only: return
    configure_torch(protocol['compute']); device=torch.device(protocol['compute']['device'])
    cache=np.load(path); waves=cache['waveforms']; labels=cache['labels']; people=cache['people']
    if set(people)!=set(protocol['development_people']) or any(p in people for p in protocol['confirmation_people']):
        raise ValueError('Participant split mismatch')
    config=protocol['eegnet']; folds=[]; predictions={}; started=time.monotonic()
    snapshot={name:sha256_file(HERE/name) for name in
        ('mi_finger_data.py','mi_finger_baseline.py','mi_finger_verify.py','mi_comparison_models.py',
         'dexterous_hand_policy.py','test_finger_pipeline.py','test_finger_model.py')}
    snapshot_path=RUN/'source_snapshot.json'
    if snapshot_path.exists() and json.loads(snapshot_path.read_text(encoding='utf-8'))!=snapshot:
        raise ValueError('Source changed after baseline started; do not mix folds')
    write_json(snapshot_path,snapshot)
    checkpoint_dir=RUN/'checkpoints'; checkpoint_dir.mkdir(exist_ok=True)
    for target in protocol['development_people']:
        fit_people,val_people=split_people(protocol,target)
        fit=np.isin(people,fit_people); val=np.isin(people,val_people); test=people==target
        fold_path=RUN/'folds'/f'{target}.json'
        prediction_path=RUN/'folds'/f'{target}_predictions.npz'
        if fold_path.exists():
            frozen=json.loads(fold_path.read_text(encoding='utf-8'))
            if frozen['protocol_sha256']!=sha256_file(RUN/'protocol.json') or frozen['cache_sha256']!=sha256_file(path):
                raise ValueError('Frozen fold provenance mismatch')
            folds.append(frozen)
            if not prediction_path.exists(): raise ValueError('Missing frozen fold predictions')
            continue
        y=labels[test]; methods={}; pred=dict(labels=y,trial_id=cache['trial_id'][test])
        diagnostics=[('bandpower_ERD_LDA','features',list(range(8))),
                     ('motor4_LDA','features',[0,1,2,3]),('occipital2_LDA','features',[6,7]),
                     ('precue8_LDA','precue',list(range(8)))]
        for name,key,channels in diagnostics:
            x=cache[key][...,channels].reshape(len(labels),-1)
            guess,elapsed=fit_lda(x[fit],labels[fit],x[test])
            methods[name]=metrics(y,guess)|dict(pc_target_inference_seconds=elapsed)
            pred[name]=guess
        lookup={}
        for run,index in zip(cache['run_number'][test],cache['trial_index'][test]):
            source=fit & (cache['run_number']==run) & (cache['trial_index']==index)
            if not source.any(): raise ValueError('Trial-index lookup has no source examples')
            lookup[(int(run),int(index))]=int(np.argmax(np.bincount(labels[source],minlength=5)))
        guess=np.array([lookup[(int(r),int(i))] for r,i in zip(cache['run_number'][test],cache['trial_index'][test])])
        methods['time_only_lookup']=metrics(y,guess); pred['time_only_lookup']=guess
        mean,scale=channel_scaler(waves[fit])
        train_x=normalized_tensor(waves[fit],mean,scale,device); val_x=normalized_tensor(waves[val],mean,scale,device)
        target_x=normalized_tensor(waves[test],mean,scale,device)
        seed_results=[]; cpu_max_error=0.; cpu_predictions_exact=True
        for seed in config['seeds']:
            model,training=train_network(train_x,labels[fit],val_x,labels[val],people[val],config,seed,device)
            torch.cuda.synchronize(); tick=time.perf_counter()
            logits=network_logits(model,target_x); torch.cuda.synchronize(); elapsed=time.perf_counter()-tick
            prediction=logits.argmax(axis=1)
            torch.save(dict(state_dict={k:v.detach().cpu() for k,v in model.state_dict().items()},mean=torch.tensor(mean),
                            scale=torch.tensor(scale),channels=FIXED,labels=protocol['labels'],control_enabled=False),
                       checkpoint_dir/f'{target}_seed{seed}.pt')
            model=model.cpu(); cpu_x=target_x.cpu(); cpu_tick=time.perf_counter()
            cpu_logits=network_logits(model,cpu_x); cpu_elapsed=time.perf_counter()-cpu_tick
            error=float(abs(cpu_logits-logits).max()); exact=bool(np.array_equal(cpu_logits.argmax(axis=1),prediction))
            if not exact or error>1e-4: raise ValueError('CPU/GPU prediction mismatch')
            cpu_max_error=max(cpu_max_error,error); cpu_predictions_exact &= exact
            result=metrics(y,prediction)|dict(training=training,pc_target_inference_seconds=elapsed,
                                            pc_cpu_target_inference_seconds=cpu_elapsed)
            seed_results.append(result); pred[f'EEGNet5_seed{seed}']=prediction
            print(f'FIT {target} seed{seed} BA={result["balanced_accuracy"]:.4f} epochs={training["completed_epochs"]}',flush=True)
        methods['EEGNet5']=dict(balanced_accuracy=float(np.mean([r['balanced_accuracy'] for r in seed_results])),
                                macro_f1=float(np.mean([r['macro_f1'] for r in seed_results])),seeds=seed_results,
                                trial_count=len(y),coverage=1.0)
        fold=dict(target=target,fit_people=fit_people,validation_people=val_people,methods=methods,
                  protocol_sha256=sha256_file(RUN/'protocol.json'),cache_sha256=sha256_file(path),
                  cpu_logits_max_abs_error=cpu_max_error,cpu_predictions_exact=cpu_predictions_exact)
        fold_path.parent.mkdir(exist_ok=True); np.savez_compressed(prediction_path,**pred)
        write_json(fold_path,fold); folds.append(fold)
        write_json(RUN/'progress.json',dict(completed_folds=len(folds),total_folds=16,elapsed_seconds=time.monotonic()-started,
                                          confirmation_people_not_used=protocol['confirmation_people']))
        del train_x,val_x,target_x; torch.cuda.empty_cache()
    summary={name:dict(mean_balanced_accuracy=float(np.mean([f['methods'][name]['balanced_accuracy'] for f in folds])),
                       mean_macro_f1=float(np.mean([f['methods'][name]['macro_f1'] for f in folds])),
                       person_ba_std=float(np.std([f['methods'][name]['balanced_accuracy'] for f in folds],ddof=1)))
             for name in folds[0]['methods']}
    gain=np.array([f['methods']['EEGNet5']['balanced_accuracy']-f['methods']['bandpower_ERD_LDA']['balanced_accuracy'] for f in folds])
    rng=np.random.default_rng(protocol['bootstrap']['seed'])
    boot=gain[rng.integers(0,len(gain),size=(protocol['bootstrap']['draws'],len(gain)))].mean(axis=1)
    ci=np.quantile(boot,[.025,.975]).tolist(); gate=protocol['continuation_gate']
    passing=(summary['EEGNet5']['mean_balanced_accuracy']>=gate['mean_ba_at_least'] and gain.mean()>=gate['EEGNet_gain_over_LDA_at_least'] and ci[0]>0)
    write_json(RUN/'results.json',dict(protocol_sha256=sha256_file(RUN/'protocol.json'),cache_sha256=sha256_file(path),
        folds=folds,summary=summary,paired_EEGNet_minus_LDA_mean=float(gain.mean()),paired_95_ci=ci,
        numerical_continuation_gate_passed=bool(passing),promotion_gate_passed=False,
        unresolved_task_instructions_and_visual_confound=True,confirmation_people_not_used=protocol['confirmation_people'],
        pc_total_seconds=time.monotonic()-started,torch_version=torch.__version__,numpy_version=np.__version__,
        cuda_device=torch.cuda.get_device_name(device),board_accessed=False,control_enabled=False))
    print('BASELINE COMPLETE '+json.dumps(summary),flush=True)


if __name__=='__main__': main()

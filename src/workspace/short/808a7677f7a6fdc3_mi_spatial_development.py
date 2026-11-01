"""Bounded CSP/filter-bank CSP development: fixed cap, untouched final subjects."""
import argparse
from datetime import datetime
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

import mne
import numpy as np
from scipy import signal, linalg
import scipy
import sklearn
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.preprocessing import StandardScaler

from mi_physionet_evaluate import bootstrap_ci,subject_metrics

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pynq_guardianloop'))
from cyton_sqi import CausalEEGFilter
from mi_features import CHANNELS,WINDOW_SAMPLES
from mi_spatial import normalized_covariance,projected_features,linear_scores

BANDS=((8,12),(18,26),(8,30),(12,16),(16,20),(20,24),(24,30))
METHODS={'C3_C4_power':([0,1],(2,3),None),'eight_power':([0,1],tuple(range(8)),None),
         'CSP_LDA':([2],tuple(range(8)),4),'FBCSP_LDA':([0,3,4,5,6],tuple(range(8)),2)}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def read_record(path,subject,run):
    raw=mne.io.read_raw_edf(path,preload=False,verbose='ERROR')
    rate=raw.info['sfreq']
    if rate not in (128,160):raise ValueError('Unexpected EDF sample rate')
    names=[name.rstrip('.').upper() for name in raw.ch_names]
    if len(set(names))!=len(names) or not set(CHANNELS).issubset(names):raise ValueError('Missing fixed electrodes')
    values=raw.get_data(picks=[names.index(name) for name in CHANNELS]).T*1e6
    ratio=Fraction(250,int(rate));up,down=ratio.numerator,ratio.denominator
    half=10*max(up,down)
    fir=up*signal.firwin(2*half+1,1/max(up,down),window=('kaiser',5))
    # One-directional FIR: retain group delay rather than shifting into future data.
    converted=signal.upfirdn(fir,values,up=up,down=down,axis=0)[:int(np.ceil(len(values)*up/down))]
    conditioned=CausalEEGFilter().process(converted)
    bands=[signal.sosfilt(signal.butter(4,band,fs=250,btype='bandpass',output='sos'),conditioned,axis=0)
           for band in BANDS]
    covariance=[];metadata=[]
    for event in raw.annotations:
        if event['description'] not in ('T1','T2') or event['duration']<4:continue
        start=round((float(event['onset'])+1)*250)
        windows=[band[start:start+WINDOW_SAMPLES] for band in bands]
        if any(len(w)!=WINDOW_SAMPLES for w in windows):continue
        covariance.append(np.stack([normalized_covariance(w) for w in windows]))
        metadata.append({'subject':subject,'run':run,'onset_s':float(event['onset']),
                         'label':0 if event['description']=='T1' else 1,'edf_rate_hz':rate,
                         'conversion_delay_s':half/(rate*up),'file':path.name})
    if not covariance:raise ValueError('No complete MI trials: '+str(path))
    return np.stack(covariance),metadata


def spatial_filters(covs,labels,method):
    bands,channels,components=METHODS[method]
    if components is None:
        return np.repeat(np.eye(8)[list(channels)][None],len(bands),axis=0)
    filters=[]
    for band in bands:
        means=[covs[labels==label,band].mean(axis=0) for label in (0,1)]
        regularized=[.9*cov+.1*np.eye(8)/8 for cov in means]
        eigenvalues,vectors=linalg.eigh(regularized[0],regularized[0]+regularized[1])
        order=np.argsort(np.abs(eigenvalues-.5))[::-1][:components]
        filters.append(vectors[:,order].T)
    return np.stack(filters)


def fit(covs,labels,method):
    if set(labels)!={0,1}:raise ValueError('Both imagery labels required in training')
    filters=spatial_filters(covs,labels,method)
    features=projected_features(covs[:,METHODS[method][0]],filters)
    scaler=StandardScaler().fit(features)
    lda=LinearDiscriminantAnalysis(solver='lsqr',shrinkage='auto').fit(scaler.transform(features),labels)
    return filters,scaler,lda


def predict(covs,method,fitted):
    filters,scaler,lda=fitted
    selected=covs[:,METHODS[method][0]]
    features=projected_features(selected,filters)
    expected=lda.decision_function(scaler.transform(features))
    actual=linear_scores(selected,filters,scaler.mean_,scaler.scale_,lda.coef_[0],lda.intercept_[0])
    np.testing.assert_allclose(actual,expected,atol=1e-10,rtol=1e-10)
    assert np.array_equal(actual>=0,lda.predict(scaler.transform(features))==1)
    return (actual>=0).astype(int),actual,float(np.max(np.abs(actual-expected)))


def metrics(truth,predicted,subjects):
    rows=subject_metrics(truth,predicted,subjects)
    values=[row['balanced_accuracy'] for row in rows]
    return {'mean_subject_balanced_accuracy':float(np.mean(values)),
            'mean_subject_macro_f1':float(np.mean([r['macro_f1'] for r in rows])),
            'subject_bootstrap_95_ci':bootstrap_ci(values,20261001),'per_subject':rows}


def export(path,method,fitted):
    filters,scaler,lda=fitted
    metadata={'channels':CHANNELS,'bands_hz':[BANDS[i] for i in METHODS[method][0]],'method':method,
              'sample_rate_hz':250,'window_samples':750,'epoch_after_cue_s':[1,4],
              'status':'development_only','promotion_gate_passed':False,'control_enabled':False,
              'feature':'log projected trace-normalized sample covariance',
              'training_subjects':[1,70],'reference_domain':'EEGMMIDB; Cyton transfer unverified'}
    np.savez(path,filters=filters,mean=scaler.mean_,scale=scaler.scale_,coef=lda.coef_[0],
             intercept=lda.intercept_[0],metadata=json.dumps(metadata))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,default=Path('D:/ican/datasets/EEGMMIDB'))
    parser.add_argument('--output',type=Path,default=HERE/'output/mi_spatial_dev_20261001')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    plan=HERE/'MI_SPATIAL_DEV_PLAN.md'
    manifest=json.loads((args.data_root/'mi_download_manifest_001_109.json').read_text())
    expected={row['path']:row['sha256'] for row in manifest}
    code_paths=[Path(__file__),plan,HERE.parent/'pynq_guardianloop/mi_spatial.py',
                HERE.parent/'pynq_guardianloop/cyton_sqi.py']
    save(args.output/'provenance.json',{'started_at_local':datetime.now().isoformat(),
         'source_code_sha256':{str(p):sha(p) for p in code_paths},'subjects_read':[1,89],
         'final_subjects_90_109_read':False,'channels':CHANNELS,'bands_hz':BANDS,
         'software':{'mne':mne.__version__,'numpy':np.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__}})
    matrices=[];meta=[];sources={}
    for subject in range(1,90):
        for run in (4,8,12):
            relative=f'S{subject:03d}/S{subject:03d}R{run:02d}.edf';path=args.data_root/relative
            digest=sha(path)
            if digest!=expected[relative]:raise ValueError('EDF hash mismatch: '+relative)
            x,rows=read_record(path,subject,run);matrices.append(x);meta.extend(rows);sources[relative]=digest
        if subject%10==0 or subject==89:print('EXTRACTED',subject,flush=True)
    covs=np.concatenate(matrices);labels=np.array([r['label'] for r in meta]);subjects=np.array([r['subject'] for r in meta]);runs=np.array([r['run'] for r in meta])
    np.savez(args.output/'trial_covariances.npz',covariances=covs,labels=labels,subjects=subjects,runs=runs)
    save(args.output/'trial_manifest.json',meta);save(args.output/'edf_sha256.json',sources)
    training=subjects<=70;validation=subjects>=71
    assert set(subjects[training]).isdisjoint(subjects[validation])
    cross={};personal={};predictions={};fitted={}
    for method in METHODS:
        fitted[method]=fit(covs[training],labels[training],method)
        pred,scores,error=predict(covs[validation],method,fitted[method])
        cross[method]={**metrics(labels[validation],pred,subjects[validation]),'portable_max_abs_error':error}
        predictions[method]={'cross_subject':[dict(meta[i],prediction=int(p),score=float(s)) for i,p,s in zip(np.flatnonzero(validation),pred,scores)],'personal':[]}
        subject_rows=[]
        for subject in range(1,90):
            calibration=(subjects==subject)&np.isin(runs,[4,8]);future=(subjects==subject)&(runs==12)
            assert set(np.flatnonzero(calibration)).isdisjoint(np.flatnonzero(future))
            local=fit(covs[calibration],labels[calibration],method)
            p,s,e=predict(covs[future],method,local)
            row=metrics(labels[future],p,subjects[future])['per_subject'][0]
            row.update(calibration_trials=int(calibration.sum()),portable_max_abs_error=e)
            subject_rows.append(row)
            predictions[method]['personal'].extend([dict(meta[i],prediction=int(v),score=float(score))
                                                  for i,v,score in zip(np.flatnonzero(future),p,s)])
        def summarize(rows):
            values=[r['balanced_accuracy'] for r in rows]
            return {'mean_subject_balanced_accuracy':float(np.mean(values)),
                    'subject_bootstrap_95_ci':bootstrap_ci(values,20261001),'per_subject':rows}
        personal[method]={'selection_1_70':summarize(subject_rows[:70]),'development_71_89':summarize(subject_rows[70:])}
        print('METHOD',method,'cross',cross[method]['mean_subject_balanced_accuracy'],
              'personal_selection',personal[method]['selection_1_70']['mean_subject_balanced_accuracy'],flush=True)
    selected_cross=max(cross,key=lambda name:cross[name]['mean_subject_balanced_accuracy'])
    selected_personal=max(personal,key=lambda name:personal[name]['selection_1_70']['mean_subject_balanced_accuracy'])
    c=cross[selected_cross];p=personal[selected_personal]['development_71_89']
    report={'scope':'development only; final exposed subjects not read; no wearable validation or control',
            'cross_subject':cross,'personal_calibrated':personal,'selected_cross_subject':selected_cross,
            'selected_personal_by_subjects_1_70':selected_personal,
            'cross_development_continue':bool(c['mean_subject_balanced_accuracy']>=.60 and c['subject_bootstrap_95_ci'][0]>.50),
            'personal_development_continue':bool(p['mean_subject_balanced_accuracy']>=.65 and p['subject_bootstrap_95_ci'][0]>.50),
            'promotion_gate_passed':False,'control_enabled':False,'all_subjects_retained':True,
            'trial_counts':{'train':int(training.sum()),'development':int(validation.sum())}}
    save(args.output/'development.json',report);save(args.output/'predictions.json',predictions)
    export(args.output/'cross_development_model.npz',selected_cross,fitted[selected_cross])
    print(json.dumps({key:report[key] for key in ('selected_cross_subject','selected_personal_by_subjects_1_70',
                      'cross_development_continue','personal_development_continue','promotion_gate_passed')},indent=2),flush=True)


if __name__=='__main__':main()

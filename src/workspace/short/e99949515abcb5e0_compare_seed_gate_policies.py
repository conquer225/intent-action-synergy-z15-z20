"""Frozen factorial policy comparison using existing participant-held-out weights."""
import csv
import json
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from threadpoolctl import threadpool_limits

from .emotion_baseline import sha256
from .seed_gated_evaluation import OUTPUT as PREVIOUS, INITIAL, metrics
from .seed_fixed8_experiment import INDICES, trial_names
from .seed_matched_preprocessing import to_simulated_250
from .seed_gate_policy import GatePolicy

OUTPUT=Path(__file__).parent/'output/seed_gate_policy_comparison_20260926'
CASES=[('clean','soft_reset'),('flat','soft_reset'),('burst','soft_reset'),
       ('gap','strict_retain'),('gap','soft_reset'),('gap','soft_retain')]


def run_record(record):
    with threadpool_limits(limits=1):
        assert sha256(Path(record['path']))==record['sha256']
        content=loadmat(record['path'])
        weights=dict(np.load(PREVIOUS/('fold_%02d.npz'%record['subject'])))
        engines={(c,p):GatePolicy(weights,soft_warning=p.startswith('soft'),retain_short_gap=p.endswith('retain')) for c,p in CASES}
        stats={k:{'cm':np.zeros((3,3),int),'duration':np.zeros(3),'states':Counter(),'reasons':Counter(),
                  'warning_predictions':0,'retained_gaps':0,'overlapping_fault_predictions':0,'recoveries':[],
                  'first_output_seconds':None} for k in engines}
        rows=[]
        elapsed=0
        for trial,name in enumerate(trial_names(content),1):
            target=int(record['labels'][trial-1])
            values=to_simulated_250(np.asarray(content[name][list(INDICES)],float).T)
            end=len(values)//500*500
            for key,engine in engines.items():
                condition,policy=key
                engine.begin_trial()
                summary=stats[key]
                summary['duration'][target+1]+=end/250
                recovery=None
                for start in range(0,end,500):
                    t=start/250
                    section=values[start:start+500].copy()
                    if 90<=t<94:
                        if condition=='flat': section[:,6:8]=0
                        elif condition=='burst': section[:,0]+=1500*np.sin(2*np.pi*12*np.arange(start,start+500)/250)
                        elif condition=='gap':
                            if t==90:
                                event=engine.gap(4)
                                summary['states']['reset']+=1
                                summary['retained_gaps']+=int(event['baseline_retained'])
                            continue
                    for event in engine.feed_block(section):
                        summary['states'][event['state']]+=1
                        if event['state']=='rejected': summary['reasons'][event['reason']]+=1
                        if event['state']!='prediction': continue
                        pred=event['class_id']
                        warning=bool(event.get('warning',False))
                        summary['warning_predictions']+=int(warning)
                        summary['cm'][target+1,pred+1]+=1
                        if summary['first_output_seconds'] is None: summary['first_output_seconds']=elapsed+t+2
                        if condition!='clean':
                            if t+2>90 and t+2-12<94: summary['overlapping_fault_predictions']+=1
                            if t+2-12>=94 and recovery is None: recovery=t+2-94
                        rows.append([condition,policy,record['subject'],record['session'],trial,t+2,target,pred,int(warning)])
                if condition!='clean': summary['recoveries'].append({'trial':trial,'seconds':recovery,'censor_seconds':end/250-94})
            elapsed+=end/250
        result=[]
        for (condition,policy),summary in stats.items():
            summary['cm']=summary['cm'].tolist()
            summary['duration']=summary['duration'].tolist()
            result.append({'condition':condition,'policy':policy,**summary})
        stem=str(record['subject'])+'_'+str(record['session'])
        with (OUTPUT/(stem+'.csv')).open('w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f)
            writer.writerow(['condition','policy','subject','session','trial','end_seconds','target','prediction','warning'])
            writer.writerows(rows)
        report={'subject':record['subject'],'session':record['session'],'results':result}
        (OUTPUT/(stem+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        return report


def summarize(reports):
    for path in sorted(PREVIOUS.glob('*_20*.json')):
        previous=json.loads(path.read_text())
        reports.append({**previous,'results':[{**s,'policy':'strict_reset' if s['gated'] else 'no_gate'} for s in previous['results']]})
    combinations=sorted({(s['condition'],s['policy']) for r in reports for s in r['results']})
    methods={}
    for condition,policy in combinations:
        participants=[]
        for subject in range(1,16):
            selected=[s for r in reports if r['subject']==subject for s in r['results'] if (s['condition'],s['policy'])==(condition,policy)]
            assert len(selected)==3
            cm=np.sum([s['cm'] for s in selected],axis=0)
            duration=np.sum([s['duration'] for s in selected],axis=0)
            assert np.all(12*cm.sum(axis=1)<=duration)
            participants.append({'subject':subject,**metrics(cm,duration)})
        selected=[s for r in reports for s in r['results'] if (s['condition'],s['policy'])==(condition,policy)]
        recovered=[v['seconds'] for s in selected for v in s['recoveries']]
        means={}
        for metric in ('accepted_balanced_accuracy','accepted_macro_f1','coverage','balanced_correct_output_yield'):
            values=[p[metric] for p in participants]
            means['mean_'+metric]=None if None in values else float(np.mean(values))
        methods[condition+'_'+policy]={'participants':participants,**means,
            'warning_predictions':sum(s.get('warning_predictions',0) for s in selected),
            'retained_gaps':sum(s.get('retained_gaps',0) for s in selected),
            'overlapping_fault_predictions':sum(s.get('overlapping_fault_predictions',0) for s in selected) if policy not in ('strict_reset','no_gate') else None,
            'recovery_total':len(recovered),'recovery_censored':sum(v is None for v in recovered),
            'median_uncensored_recovery_seconds':float(np.median([v for v in recovered if v is not None])) if any(v is not None for v in recovered) else None}
    comparisons={}
    draws=np.random.default_rng(20260926).integers(0,15,(20000,15))
    for a,b,metric in [('clean_soft_reset','clean_strict_reset','balanced_correct_output_yield'),
                       ('gap_soft_retain','gap_soft_reset','balanced_correct_output_yield'),
                       ('clean_soft_reset','clean_no_gate','accepted_balanced_accuracy')]:
        first=[p[metric] for p in methods[a]['participants']]
        second=[p[metric] for p in methods[b]['participants']]
        ci=None; gain=None
        if None not in first+second:
            delta=np.asarray(first)-second
            gain=float(delta.mean())
            ci=np.quantile(delta[draws].mean(axis=1),[.05/6,1-.05/6]).tolist()
        comparisons[a+'_minus_'+b]={'metric':metric,'mean_gain':gain,'simultaneous_ci98333':ci}
    result={'methods':methods,'primary_comparisons':comparisons,'board_changed':False,
            'interpretation':'Exploratory fixed-policy comparison; no new accuracy claim for wearer; no deployment selection on these test labels'}
    (OUTPUT/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:{a:b for a,b in v.items() if a!='participants'} for k,v in methods.items()},indent=2),flush=True)


def main():
    started=time.time()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if (OUTPUT/'protocol.json').exists(): raise FileExistsError('Preserve existing run; choose a new OUTPUT')
    old=json.loads((PREVIOUS/'protocol.json').read_text())
    for path,digest in old['hashes'].items(): assert sha256(Path(path))==digest
    source=json.loads((INITIAL/'manifest.json').read_text())
    paths=[Path(__file__),Path(__file__).with_name('seed_gate_policy.py'),INITIAL/'manifest.json',PREVIOUS/'protocol.json',PREVIOUS/'results.json']
    paths+=sorted(PREVIOUS.glob('fold_*.npz'))+sorted(PREVIOUS.glob('*_20*.json'))
    protocol={'hypothesis':'Separating statistical soft warnings and retaining fresh calibrated baseline across short gaps improves useful output without erasing hard-fault rejection',
        'montage':['F3','F4','C3','C4','T7','T8','O1','O2'],'split':'unchanged15LOSO,45sessions675films; reuse frozen source-only trained fold weights',
        'soft':'Keep original absolute heuristics and clipping/flat/rail checks. Adaptive-only failure warns; continue filter and prediction but freeze SQI and feature-mean update on warned windows.',
        'retain':'Same stream only, known gap0<seconds<=5, >=5 trusted windows, finite baseline, last trusted complete window within30s including gap; reject invalidates freshness. Reset filters/pending/old prediction regardless.',
        'thresholds':'Fixed engineering ablation; no search, no fitting to test labels; not a proven physiological standard',
        'cases':CASES,'controls':'Cached exact previous strict_reset and no_gate; non-gap retain arms identical by construction',
        'faults':'Identical90-94s eachfilm; O1O2 flat; F3 1500uV12Hz burst; missingpacket gap4s',
        'primary_tests':['clean soft vs strict correct-output yield >0','gap soft retain vs soft reset correct-output yield >0','clean soft vs no gate BA noninferiority margin -0.02'],
        'statistics':'Participant bootstrap20000 seed20260926; Bonferroni98.333% intervals for3primary comparisons; failures and abstentions retained',
        'limitations':['Exploratory reused cohort; not independent validation','Unknown SEED upstream reference, synthetic200to250Hz, missingrest',
                       'First calibration is film EEG, not neutral baseline','No real contact-fault labels','No parameter search or automatic deployment','Short gap is known retrospectively on resume; live implementation must not use future gap duration'],
        'hashes':{str(p):sha256(p) for p in paths}}
    (OUTPUT/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    reports=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        jobs=[pool.submit(run_record,{**r,'labels':source['labels']}) for r in source['records']]
        for job in as_completed(jobs):
            r=job.result();reports.append(r)
            print('SESSION',len(reports),'/45',r['subject'],r['session'],round(time.time()-started,1),flush=True)
    summarize(reports)


if __name__=='__main__':main()

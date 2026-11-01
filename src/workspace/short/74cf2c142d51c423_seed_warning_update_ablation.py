"""Single-factor audit: keep the gate fixed, change only warned-window mean updates."""
import csv
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from . import compare_seed_gate_policies as comparison
from .emotion_baseline import sha256
from .seed_gate_policy import GatePolicy
from seed_quality_runtime import SeedQualityRuntime

FROZEN=comparison.OUTPUT
OUTPUT=Path(__file__).parent/'output/seed_warning_update_ablation_20260926'
CASES=[('clean','soft_reset'),('flat','soft_reset'),('burst','soft_reset'),('gap','soft_reset'),('gap','soft_retain')]


class UpdatingWarningPolicy(GatePolicy):
    def _accept_feature(self, feature):
        if self.soft_warning and self.window_warning:
            self.window_warning=False
            event=SeedQualityRuntime._accept_feature(self,feature)
            event['warning']=True
            event['baseline_updated']=event['state'] in ('prediction','calibrating')
            # Updating the mean does NOT grant trusted freshness to a warning.
            return event
        return super()._accept_feature(feature)


def worker(record):
    comparison.OUTPUT=OUTPUT
    comparison.CASES=CASES
    comparison.GatePolicy=UpdatingWarningPolicy
    return comparison.run_record(record)


def main():
    started=time.time()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if (OUTPUT/'protocol.json').exists():raise FileExistsError('Preserve existing experiment')
    frozen=json.loads((FROZEN/'protocol.json').read_text())
    for p,d in frozen['hashes'].items():assert sha256(Path(p))==d
    source=json.loads((comparison.INITIAL/'manifest.json').read_text())
    paths=[Path(__file__),Path(comparison.__file__),Path(__file__).with_name('seed_gate_policy.py'),FROZEN/'protocol.json',FROZEN/'results.json']
    paths+=sorted(FROZEN.glob('*_20*.json'))+sorted(FROZEN.glob('*_20*.csv'))
    protocol={'hypothesis':'Freezing the personal mean on soft-warning windows contributes to lost classification performance',
        'change':'Only mean update after warning prediction changes; same hard gate, SQI freeze, filters, weights, held-out folds, fault scenarios, and trusted freshness rule',
        'montage':['F3','F4','C3','C4','T7','T8','O1','O2'],'cases':CASES,
        'no_search':'One predeclared alternative. No refit or test-label selection. Exploratory reused15subject cohort.',
        'primary_tests':['clean BA update-minus-freeze paired improvement','clean BA update-minus-no-gate lower > -0.02'],
        'statistics':'15participant bootstrap20000 seed20260926,97.5% individual intervals Bonferroni2tests',
        'audit':'For non-gap cases require exact same output times/labels/warning flags; gap retention count may depend on past calibration counts and will be checked',
        'deployment':'none; warning data must not be called clean merely because updating helps',
        'hashes':{str(p):sha256(p) for p in paths}}
    (OUTPUT/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    reports=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        jobs=[pool.submit(worker,{**r,'labels':source['labels']}) for r in source['records']]
        for job in as_completed(jobs):
            reports.append(job.result())
            print('SESSION',len(reports),'/45',round(time.time()-started,1),flush=True)
    audit(reports)


def audit(reports):
    protocol=json.loads((OUTPUT/'protocol.json').read_text())
    source_checks={}
    for name,digest in protocol['hashes'].items():
        path=Path(name)
        if path.resolve()==Path(__file__).resolve() and sha256(path)!=digest:
            path=OUTPUT/'run_source_frozen.py'
        assert sha256(path)==digest,name
        source_checks[name]=str(path)
    methods={}
    old=json.loads((FROZEN/'results.json').read_text())
    matching_rows=0
    changed_gap_rows=[]
    subsets={'warning':[0,0,0],'no_warning':[0,0,0]}
    for report in reports:
        stem=str(report['subject'])+'_'+str(report['session'])
        with (OUTPUT/(stem+'.csv')).open() as f:new=list(csv.DictReader(f))
        with (FROZEN/(stem+'.csv')).open() as f:prior=[r for r in csv.DictReader(f) if (r['condition'],r['policy']) in CASES]
        identity=lambda r:tuple(r[k] for k in ('condition','policy','subject','session','trial','end_seconds','target','warning'))
        assert [identity(r) for r in new if r['condition']!='gap']==[identity(r) for r in prior if r['condition']!='gap']
        prior_map={identity(r):r for r in prior}
        new_map={identity(r):r for r in new}
        matching_rows+=len(prior_map.keys() & new_map.keys())
        for key in new_map.keys()-prior_map.keys():
            changed_gap_rows.append({'direction':'new_only','identity':key})
        for key in prior_map.keys()-new_map.keys():
            changed_gap_rows.append({'direction':'freeze_only','identity':key})
        for key,a in new_map.items():
            if a['condition']!='clean':continue
            b=prior_map[key]
            counts=subsets['warning' if a['warning']=='1' else 'no_warning']
            counts[0]+=1;counts[1]+=int(a['prediction']==a['target']);counts[2]+=int(b['prediction']==b['target'])
    for condition,policy in CASES:
        people=[]
        for subject in range(1,16):
            sessions=[s for r in reports if r['subject']==subject for s in r['results'] if (s['condition'],s['policy'])==(condition,policy)]
            people.append({'subject':subject,**comparison.metrics(np.sum([s['cm'] for s in sessions],axis=0),np.sum([s['duration'] for s in sessions],axis=0))})
        methods[condition+'_'+policy]={'participants':people,
            'mean_balanced_accuracy':float(np.mean([p['accepted_balanced_accuracy'] for p in people])),
            'mean_coverage':float(np.mean([p['coverage'] for p in people])),
            'mean_correct_output_yield':float(np.mean([p['balanced_correct_output_yield'] for p in people]))}
    comparisons={}
    new=np.array([p['accepted_balanced_accuracy'] for p in methods['clean_soft_reset']['participants']])
    draws=np.random.default_rng(20260926).integers(0,15,(20000,15))
    for name in ('clean_soft_reset','clean_no_gate'):
        previous=np.array([p['accepted_balanced_accuracy'] for p in old['methods'][name]['participants']])
        delta=new-previous
        ci=np.quantile(delta[draws].mean(axis=1),[.0125,.9875]).tolist()
        comparisons[name]={'gain':float(delta.mean()),'ci975':ci,'passes':ci[0]>(-.02 if name=='clean_no_gate' else 0)}
    result={'methods':methods,'primary_comparisons':comparisons,'exact_matching_output_rows':matching_rows,
        'frozen_hash_checks':source_checks,'audit_source_sha256':sha256(Path(__file__)),
        'gap_output_set_changes':changed_gap_rows,
        'audit_note':'Non-gap output identities identical as predeclared. Gap cases may complete calibration earlier when warning updates count; all extra outputs included in metrics, not discarded. Run-time source archived separately.',
        'clean_subgroups_pooled_counts_n_update_correct_freeze_correct':subsets,
        'subgroup_caution':'Descriptive pooled counts; not independent-window inference or participant-averaged BA',
        'board_changed':False}
    (OUTPUT/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({**result,'methods':{k:{a:b for a,b in v.items() if a!='participants'} for k,v in methods.items()}},indent=2),flush=True)


if __name__=='__main__':main()

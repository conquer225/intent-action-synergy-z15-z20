"""Frozen participant-held-out replay of the deployed SEED gate; no board writes."""
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
from .seed_causal_normalization import past_center
from .seed_covariance_diagnosis import INITIAL, model_for
from .seed_export_candidate import linear_parameters
from .seed_fixed8_experiment import INDICES, trial_names
from .seed_matched_preprocessing import OUTPUT as CACHE, ROOT, to_simulated_250
from seed_quality_runtime import SeedQualityRuntime

OUTPUT = Path(__file__).parent / 'output/seed_gated_evaluation_20260926'
CONDITIONS = ('clean', 'flat', 'burst', 'gap')


def metrics(confusion, duration):
    cm, duration = np.asarray(confusion, float), np.asarray(duration, float)
    support = cm.sum(axis=1)
    recalls = np.divide(cm.diagonal(), support, out=np.zeros(3), where=support > 0)
    fden = support + cm.sum(axis=0)
    return {'predictions': int(cm.sum()), 'support': support.astype(int).tolist(),
            'accepted_accuracy': float(cm.trace()/cm.sum()) if cm.sum() else None,
            'accepted_balanced_accuracy': float(recalls.mean()) if (support > 0).all() else None,
            'accepted_macro_f1': float(np.divide(2*cm.diagonal(), fden, out=np.zeros(3), where=fden > 0).mean()) if (support > 0).all() else None,
            'coverage': float(12*cm.sum()/duration.sum()),
            'class_coverage': (12*support/duration).tolist(),
            'balanced_correct_output_yield': float(np.mean(12*cm.diagonal()/duration))}


def replay_record(record):
    started = time.time()
    with threadpool_limits(limits=1):
        path = Path(record['path'])
        if sha256(path) != record['sha256']:
            raise ValueError('Raw source hash changed: '+str(path))
        raw = loadmat(path)
        weights = dict(np.load(OUTPUT / ('fold_%02d.npz' % record['subject'])))
        engines = {(c, g): SeedQualityRuntime(weights) for c in CONDITIONS for g in (False, True)}
        summaries = {k: {'cm': np.zeros((3,3), int), 'duration': np.zeros(3), 'states': Counter(),
                         'reasons': Counter(), 'first_output_seconds': None, 'recoveries': []} for k in engines}
        rows = []
        elapsed = 0.
        for trial, name in enumerate(trial_names(raw), 1):
            target = int(record['labels'][trial-1])
            values = to_simulated_250(np.asarray(raw[name][list(INDICES)], float).T)
            end = len(values)//500*500
            for (condition, gated), engine in engines.items():
                # Film files lack inter-trial rest: do not mix tails or invent continuity.
                engine._reset_signal()
                engine.pending = np.empty((0, 8))
                summary = summaries[(condition, gated)]
                summary['duration'][target+1] += end/250
                recovery = None
                for start in range(0, end, 500):
                    section = values[start:start+500].copy()
                    t = start/250
                    if 90 <= t < 94:
                        if condition == 'flat':
                            section[:,6:8] = 0
                        elif condition == 'burst':
                            section[:,0] += 1500*np.sin(2*np.pi*12*np.arange(start,start+500)/250)
                        elif condition == 'gap':
                            events = [engine.disconnect('injected_missing_packets')] if t == 90 else []
                            for event in events:
                                summary['states'][event['state']] += 1
                            continue
                    if gated:
                        events = engine.append(section)
                    else:
                        conditioned = engine.prefilter.process(section)
                        features = engine.features.process(engine.resampler.process(conditioned))
                        events = [engine._accept_feature(f) for f in features]
                    for event in events:
                        summary['states'][event['state']] += 1
                        if event['state'] == 'rejected':
                            summary['reasons'][event['reason']] += 1
                        if event['state'] != 'prediction':
                            continue
                        prediction = event['class_id']
                        summary['cm'][target+1,prediction+1] += 1
                        if summary['first_output_seconds'] is None:
                            summary['first_output_seconds'] = elapsed+t+2
                        # Recovery requires a complete prediction window after the fault.
                        if condition != 'clean' and t+2-12 >= 94 and recovery is None:
                            recovery = t+2-94
                        rows.append([condition, int(gated), record['subject'], record['session'], trial,
                                     t+2, target, prediction])
                if condition != 'clean':
                    summary['recoveries'].append({'trial': trial, 'seconds': recovery,
                                                  'censor_seconds': end/250-94})
            elapsed += end/250
        result = []
        for (condition, gated), summary in summaries.items():
            summary['cm'] = summary['cm'].tolist()
            summary['duration'] = summary['duration'].tolist()
            result.append({'condition': condition, 'gated': gated, **summary})
        stem = str(record['subject'])+'_'+str(record['session'])
        with (OUTPUT/(stem+'.csv')).open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['condition','gated','subject','session','trial','end_seconds','target','prediction'])
            writer.writerows(rows)
        report = {'subject': record['subject'], 'session': record['session'], 'results': result,
                  'elapsed_seconds': time.time()-started}
        (OUTPUT/(stem+'.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report


def main():
    started = time.time()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT/'protocol.json').exists():
        raise FileExistsError('Use a new explicit output directory for a new run')
    source = json.loads((INITIAL/'manifest.json').read_text())
    cached_results = json.loads((CACHE/'results.json').read_text())
    assert sha256(CACHE/'features.npz') == cached_results['hashes'][str(CACHE/'features.npz')]
    protocol = {'montage': ['F3','F4','C3','C4','T7','T8','O1','O2'],
                'split': '15 LOSO participants, all45 sessions and675 films, no held-out label fitting',
                'model': 'Frozen matched clean-source expanding centering + equal-prior shrinkage LDA; no tuning',
                'gate': 'Exact deployed SeedQualityRuntime, all8 usable; no amplitude scaling or threshold changes',
                'conditions': 'clean; O1/O2 zero; F3 +1500uV 12Hz; missing packets. Fault90-94s EACH film; deterministic',
                'adaptation': 'First5 accepted12s windows, score before mean update; source clean training. Film resets filters only; gap resets everything.',
                'denominator': 'All complete2s recording segments including startup, faults, calibration and rejection; prediction covers12s, no overlap',
                'metrics': '15 participant means; conditional accuracy null if any class has no predictions; class coverage; balanced correct-output yield counts abstention as no correct output',
                'decision': 'Shadow only. Clean gate retention requires coverage >=80% of ungated AND paired BA lower95CI > -0.02; any undefined participant BA fails.',
                'limitations': ['Same exploratory cohort, not independent confirmation','SEED preprocessed200Hz synthetic250Hz is not raw Cyton',
                               'Unknown upstream reference and absent inter-film rest','Film condition labels are not wearer ground truth',
                               'Shifted accepted windows: conditional accuracy is not a paired-window accuracy comparison',
                               'Synthetic faults do not establish real contact-fault robustness'],
                'hashes': {str(p): sha256(p) for p in [Path(__file__), CACHE/'features.npz', INITIAL/'manifest.json',
                    ROOT/'pynq_guardianloop/seed_quality_runtime.py',ROOT/'pynq_guardianloop/cyton_sqi.py',
                    ROOT/'pynq_guardianloop/seed_replay_check.py']}}
    (OUTPUT/'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    data = np.load(CACHE/'features.npz')
    x,y,keys = data['matched'],data['targets'],data['keys']
    adapted = np.empty_like(x)
    eligible = np.ones(len(x), bool)
    for subject, session in np.unique(keys[:,:2], axis=0):
        indices = np.flatnonzero((keys[:,0]==subject)&(keys[:,1]==session))
        indices = indices[np.lexsort((keys[indices,3],keys[indices,2]))]
        eligible[indices[:5]] = False
        adapted[indices] = past_center(x[indices], 'expanding')
    with threadpool_limits(limits=2):
        for subject in range(1,16):
            train = eligible & (keys[:,0]!=subject)
            model = model_for('lda').fit(adapted[train], y[train])
            weight,bias = linear_parameters(model)
            np.savez(OUTPUT/('fold_%02d.npz'%subject),weight=weight,bias=bias,classes=np.array([-1,0,1]))
    records = [{**r,'labels':source['labels']} for r in source['records']]
    reports = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(replay_record,r) for r in records]
        for future in as_completed(futures):
            result = future.result()
            reports.append(result)
            print('SESSION',len(reports),'/45',result['subject'],result['session'],round(time.time()-started,1),flush=True)
    aggregate(reports, started)


def aggregate(reports, started):
    methods = {}
    for condition in CONDITIONS:
        for gated in (False,True):
            people = []
            for subject in range(1,16):
                sessions = [s for r in reports if r['subject']==subject for s in r['results']
                            if s['condition']==condition and s['gated']==gated]
                cm = np.sum([s['cm'] for s in sessions],axis=0)
                duration = np.sum([s['duration'] for s in sessions],axis=0)
                people.append({'subject':subject,**metrics(cm,duration)})
            sessions = [s for r in reports for s in r['results'] if s['condition']==condition and s['gated']==gated]
            rec = [v['seconds'] for s in sessions for v in s['recoveries']]
            first = [s['first_output_seconds'] for s in sessions]
            bas = [p['accepted_balanced_accuracy'] for p in people]
            methods[condition+('_gate' if gated else '_no_gate')] = {
                'participants':people,'mean_accepted_balanced_accuracy':float(np.mean(bas)) if None not in bas else None,
                'mean_coverage':float(np.mean([p['coverage'] for p in people])),
                'mean_balanced_correct_output_yield':float(np.mean([p['balanced_correct_output_yield'] for p in people])),
                'sessions_without_output':sum(v is None for v in first),
                'median_first_output_seconds':float(np.median([v for v in first if v is not None])) if any(v is not None for v in first) else None,
                'recovery_censored':sum(v is None for v in rec), 'recovery_total':len(rec),
                'median_uncensored_recovery_seconds':float(np.median([v for v in rec if v is not None])) if any(v is not None for v in rec) else None}
    clean, base = methods['clean_gate'],methods['clean_no_gate']
    ci = None
    if clean['mean_accepted_balanced_accuracy'] is not None:
        delta = np.array([a['accepted_balanced_accuracy']-b['accepted_balanced_accuracy'] for a,b in zip(clean['participants'],base['participants'])])
        draws = np.random.default_rng(20260926).integers(0,15,(20000,15))
        ci = np.quantile(delta[draws].mean(axis=1),[.025,.975]).tolist()
    result = {'methods':methods,'paired_clean_ba_ci95':ci,
              'clean_retention_passes':bool(ci is not None and ci[0]>-.02 and clean['mean_coverage']>=.8*base['mean_coverage']),
              'board_changed':False,'elapsed_seconds':time.time()-started}
    (OUTPUT/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:{a:b for a,b in v.items() if a!='participants'} for k,v in methods.items()},indent=2),flush=True)


if __name__ == '__main__':
    main()

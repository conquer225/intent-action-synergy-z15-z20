"""Standalone isolated replay. Never opens serial, HTTP status, services or PL."""
import json
import platform
import time
from collections import Counter
from pathlib import Path

import numpy as np
import scipy
from seed_gate_policy import GatePolicy


def run(raw, sequence, weights, gap_start=None, gap_seconds=4, retain=False):
    engine=GatePolicy(weights,retain_short_gap=retain)
    events=[];scores=[];means=[];timings=[]
    natural=set((np.flatnonzero(np.diff(sequence)%256!=1)+1).tolist())
    boundaries=sorted(natural|{0,len(raw)})
    for left,right in zip(boundaries[:-1],boundaries[1:]):
        if left in natural:
            # An 8-bit packet counter alone cannot identify elapsed outage duration.
            event=engine.gap(0,same_stream=False)
            events.append({'row_end':left,'reason':'recorded_counter_gap_duration_unknown',**event})
        cursor=left
        while cursor+500<=right:
            if gap_start is not None and cursor>=gap_start and cursor<gap_start+gap_seconds*250:
                before=engine.mean.copy()
                event=engine.gap(gap_seconds)
                if event['baseline_retained']:np.testing.assert_array_equal(engine.mean,before)
                else:assert engine.accepted_windows==0
                assert engine.last_prediction is None and engine.features.pending.shape[1]==0
                events.append({'row_end':cursor+int(gap_seconds*250),'reason':'injected_known_gap',**event})
                cursor+=int(gap_seconds*250)
                continue
            started=time.perf_counter()
            current=engine.feed_block(raw[cursor:cursor+500])
            timings.append(time.perf_counter()-started)
            for event in current:
                events.append({'row_end':cursor+500,**event})
                if event['valid']:scores.append(event['scores'])
                means.append(engine.mean.copy())
            cursor+=500
    return {'events':events,'counts':dict(Counter(e['state'] for e in events)),
            'retained_gaps':sum(bool(e.get('baseline_retained')) for e in events),
            'processing_seconds':float(sum(timings)),
            'block_median_seconds':float(np.median(timings)), 'block_p95_seconds':float(np.quantile(timings,.95)),
            'source':'offline_replay_not_live','input_seconds':len(raw)/250},np.asarray(scores).reshape(-1,3),np.asarray(means)


def main():
    data=dict(np.load('input.npz'))
    weights=dict(np.load('matched_linear_weights.npz'))
    reports={};arrays={}
    for name,raw,seq,start,gap in [
        ('recorded_natural',data['recorded'],data['sequence'],None,4),
        ('recorded_gap40',data['recorded'],data['sequence'],10050,4),
        ('synthetic_short',data['synthetic'],np.arange(len(data['synthetic']))%256,22500,4),
        ('synthetic_long',data['synthetic'],np.arange(len(data['synthetic']))%256,22500,6)]:
        for retain in (False,True):
            key=name+('_retain' if retain else '_reset')
            report,scores,means=run(raw,seq,weights,start,gap,retain)
            reports[key]=report;arrays[key+'_scores']=scores;arrays[key+'_means']=means
    Path('result').mkdir(exist_ok=True)
    np.savez('result/arrays.npz',**arrays)
    Path('result/report.json').write_text(json.dumps({'cases':reports,'environment':{'python':platform.python_version(),
        'numpy':np.__version__,'scipy':scipy.__version__,'machine':platform.machine()},
        'scope':'Engineering state and numerical parity; no emotion accuracy or PL acceleration evidence'},indent=2),encoding='utf-8')
    print(json.dumps({k:{a:b for a,b in v.items() if a!='events'} for k,v in reports.items()},indent=2))


if __name__=='__main__':main()

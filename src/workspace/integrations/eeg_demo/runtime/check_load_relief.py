"""Check primary numeric equivalence and observed latency; never claims accuracy."""
import argparse
import json
from pathlib import Path

import numpy as np


def numeric_equal(left,right,errors):
    if isinstance(left,dict) and isinstance(right,dict):
        return left.keys()==right.keys() and all(numeric_equal(left[k],right[k],errors) for k in left)
    if isinstance(left,list) and isinstance(right,list):
        return len(left)==len(right) and all(numeric_equal(a,b,errors) for a,b in zip(left,right))
    if type(left) in (float,int) and type(right) in (float,int):
        errors.append(abs(left-right))
        return bool(np.isclose(left,right,atol=1e-9,rtol=1e-9))
    return left==right


def main():
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path)
    parser.add_argument('--reference',default='original');parser.add_argument('--candidate',default='array_async')
    args=parser.parse_args();result={};windows={};reports={}
    for name in (args.reference,args.candidate):
        directory=args.folder/name
        rows=json.loads((directory/'primary_results.json').read_text())
        reports[name]=json.loads((directory/'report.json').read_text())
        windows[name]={r['result']['packets_seen']:r['result'] for r in rows if 'window' in r['result']}
        monitor=[json.loads(l) for l in (directory/'monitor.jsonl').read_text().splitlines()]
        result[name]=dict(report=reports[name],published_windows=len(windows[name]),
            normal_fatigue_windows=sum(r.get('valid') is True and r.get('state')=='NORMAL'
                                       and r.get('level') is not None for r in windows[name].values()),
            distinct_fatigue_inferences=len({r['last_inference_window'] for r in windows[name].values()
                if r.get('state')=='NORMAL' and r.get('level') is not None}),
            emotion_prediction_windows=sum((r.get('emotion') or {}).get('valid') is True for r in windows[name].values()),
            seed_prediction_rows=sum((r.get('seed') or {}).get('state')=='prediction' for r in monitor),
            seed_max_accepted_windows=max((r.get('seed') or {}).get('accepted_windows',0) for r in monitor),
            primary_resets=max((r.get('runtime') or {}).get('primary_stream_resets',0) for r in monitor))
    fields=('window','packets_seen','valid','state','level','perclos','smoothed_perclos',
            'last_inference_window','calibration_current','signal_quality','emotion','sqi')
    reference,candidate=windows[args.reference],windows[args.candidate]
    common=reference.keys() & candidate.keys();differences=[];errors=[]
    for index in sorted(common):
        if not numeric_equal({k:reference[index].get(k) for k in fields},
                             {k:candidate[index].get(k) for k in fields},errors):differences.append(index)
    complete=all(r['error'] is None and r['packets_consumed']==r['packets_expected']
                 and not r['remaining_children'] for r in reports.values())
    parity=bool(common) and reference.keys()==candidate.keys() and not differences
    before,after=reports[args.reference],reports[args.candidate]
    latency_improved=all(after[k]<=before[k] for k in ('packet_input_age_p95_ms','packet_input_age_max_ms'))
    result.update(common_windows=len(common),different_packet_indices=differences,
        missing_candidate_indices=sorted(reference.keys()-candidate.keys()),
        missing_reference_indices=sorted(candidate.keys()-reference.keys()),
        max_numeric_difference=max(errors,default=0),primary_numeric_parity=parity,
        complete_no_error=complete,latency_improved=latency_improved,
        promotion_gate=complete and parity and latency_improved,
        scope='Fixed recorded bench input; software computation/latency, not recognition accuracy or live radio/HDMI acceptance')
    (args.folder/(args.candidate+'-checks.json')).write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in reports},indent=2))
    for name in reports:
        print(json.dumps(dict(case=name,**{k:v for k,v in result[name].items() if k!='report'},
            latency_p95_ms=reports[name]['packet_input_age_p95_ms'],
            latency_max_ms=reports[name]['packet_input_age_max_ms'])))


if __name__=='__main__':main()

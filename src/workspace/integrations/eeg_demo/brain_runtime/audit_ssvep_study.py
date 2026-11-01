"""Offline collection audit; requested gaze labels are not verified physiological truth."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct

CAP = ['F3','F4','C3','C4','T7','T8','O1','O2']


def checksum(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def audit(study_path, recordings, events_path):
    data=json.loads(Path(study_path).read_text(encoding='utf-8'))
    plan=data['plan'];trials=plan['trials'];attempts=data['attempts']
    body={k:v for k,v in plan.items() if k!='digest'}
    if (plan.get('schema')!='ssvep-four-corner-study-v1' or checksum(body)!=plan['digest']
            or plan['channel_map']!=CAP or plan['stimulus_frequencies']!=[8,10,12,14]
            or plan['rest_condition']!='center_gaze_while_all_four_targets_flicker'
            or len(trials)!=20 or [r['index'] for r in trials]!=list(range(20))):
        raise ValueError('Plan integrity/layout mismatch')
    blocks=[]
    for index,phase in enumerate(('calibration','confirmation')):
        rows=trials[index*10:index*10+10]
        labels=Counter(r['requested_hz'] for r in rows)
        identities={r['block_id'] for r in rows}
        if any(r['phase']!=phase for r in rows) or labels!=Counter({8:2,10:2,12:2,14:2,0:2}) or len(identities)!=1:
            raise ValueError('Invalid prospective phase split')
        blocks.append(identities.pop())
    if blocks[0]==blocks[1] or len(attempts)>20:
        raise ValueError('Calibration/confirmation blocks overlap')
    events=[json.loads(line) for line in Path(events_path).read_text(encoding='utf-8').splitlines()]
    used=set();rows=[]
    for index,a in enumerate(attempts):
        context=dict(trials[index],study_id=plan['study_id'],plan_digest=plan['digest'],label_used_by_decoder=False)
        if any(a.get(k)!=v for k,v in context.items()):raise ValueError('Attempt relabeled or reordered')
        token=a['raw_recording_id']
        if not re.fullmatch('[0-9a-f]{16}',token) or token in used:
            raise ValueError('Unsafe or shared raw recording ID')
        used.add(token)
        folder=Path(recordings)/token
        row=dict(index=index,phase=a['phase'],requested_hz=a['requested_hz'],raw_id=token,
                 closed=a['state']=='closed',integrity=False,raw_coverage=False,
                 eligible_for_future_analysis=False,confirmed_hz=[],rejection_counts={})
        rows.append(row)
        if not (folder/'metadata.json').is_file():
            row['detail']='No raw metadata; retain as failed/pending attempt';continue
        metadata=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
        protocol=metadata.get('protocol',{})
        if (metadata.get('trial_id')!=token or metadata.get('channel_map')!=CAP
                or metadata.get('sample_rate_hz')!=250
                or metadata.get('condition_requested')!='ssvep_free_diagnostic'
                or protocol.get('study')!=context or checksum(protocol)!=metadata.get('protocol_digest')):
            raise ValueError('Raw metadata/study provenance mismatch: '+token)
        n=metadata['samples']
        sizes={'samples_i32le.bin':32,'sequence_u8.bin':1,'flags_u8.bin':1,
               'stream_index_u64le.bin':8,'arrival_mono_f64le.bin':8}
        if type(n)!=int or n<=0 or any(not (folder/name).is_file() or (folder/name).stat().st_size!=n*width for name,width in sizes.items()):
            row['detail']='Incomplete raw files; not an eligible trial';continue
        arrival=[v[0] for v in struct.iter_unpack('<d',(folder/'arrival_mono_f64le.bin').read_bytes())]
        indices=[v[0] for v in struct.iter_unpack('<Q',(folder/'stream_index_u64le.bin').read_bytes())]
        sequence=(folder/'sequence_u8.bin').read_bytes();flags=(folder/'flags_u8.bin').read_bytes()
        if (not all(math.isfinite(t) and t>=0 for t in arrival)
                or any(b<a for a,b in zip(arrival,arrival[1:]))
                or any(b!=a+1 for a,b in zip(indices,indices[1:]))
                or any(((sequence[i]-sequence[i-1])%256!=1)!=bool(flags[i]&1) for i in range(1,n))):
            row['detail']='Raw timestamp/index/sequence inconsistency';continue
        linked=[r for r in events if r.get('id')==a.get('session_id') and a.get('session_id')]
        if any(r.get('raw_recording_id')!=token or r.get('board_boot_id')!=metadata['board_boot_id'] for r in linked):
            raise ValueError('Event/raw association mismatch')
        onset=a.get('presented_monotonic');end=a.get('stopped_monotonic')
        coverage=onset is not None and end is not None and arrival[0]<=onset<end<=arrival[-1]
        decisions=[r for r in linked if r.get('event')=='window_diagnostic']
        confirmed=sorted({r['decision']['top_hz'] for r in decisions
                          if r.get('accepted') is True and isinstance(r.get('decision'),dict)})
        row.update(integrity=True,raw_coverage=coverage,
            eligible_for_future_analysis=bool(a.get('collection_complete') and coverage and linked),
            confirmed_hz=confirmed,rejection_counts=dict(Counter(r['reason'] for r in decisions)),
            sequence_gap_rows=sum(bool(f&1) for f in flags),malformed_rows=sum(bool(f&2) for f in flags))
    rest=[r for r in rows if r['phase']=='confirmation' and r['requested_hz']==0 and r['eligible_for_future_analysis']]
    return dict(study_id=plan['study_id'],plan_digest=plan['digest'],attempts=rows,
        split_traceability_verified=True,complete_collection=len(rows)==20 and all(r['closed'] for r in rows),
        eligible_confirmation_trials=sum(r['phase']=='confirmation' and r['eligible_for_future_analysis'] for r in rows),
        confirmation_rest_trials=len(rest),rest_trials_with_any_confirmed_frequency=sum(bool(r['confirmed_hz']) for r in rest),
        thresholds_fitted=False,human_accuracy_claimed=False,
        limitations=['Requested gaze is not eye-tracking ground truth.',
                     'USB receive time and browser receipt are not optical/ADC timestamps.',
                     'Failed attempts retained; calibration cannot use confirmation data.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--recordings',type=Path,required=True)
    parser.add_argument('--events',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=audit(args.study,args.recordings,args.events)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,allow_nan=False,indent=2)
    print('STUDY AUDIT SAVED: no fitting or board writes')


if __name__=='__main__':main()

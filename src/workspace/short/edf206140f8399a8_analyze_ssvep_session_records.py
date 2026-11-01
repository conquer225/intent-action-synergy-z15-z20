"""Read-only collection and diagnostic replay of existing SSVEP recordings.

No live endpoints are written, no recording is started, and no threshold is fitted.
"""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import shlex
import sys

import numpy as np

from run_soak_stage import connect, command, PROD
from ssvep_diagnostic_recording import FILES
from run_mi_arm_acceptance import dump, digest

OUT = Path(__file__).parent/'output/ssvep_wait_replay_20261003'
PYTHON = '/usr/local/share/pynq-venv/bin/python3'
CAP = ['F3','F4','C3','C4','T7','T8','O1','O2']


def collect():
    OUT.mkdir(exist_ok=False)
    dump(OUT/'PLAN.json',dict(created_at=datetime.now().astimezone().isoformat(),
        hypothesis='Existing cued matches need not pass free-choice rejection and continuous confirmation.',
        falsification='Quality-passed post-onset candidates consistently satisfy the frozen free policy.',
        channels=CAP, decoder_channels=['O1','O2'], thresholds_unchanged=[.55,.10],
        replay_filter='same frozen causal coefficients, fresh state per raw capture; not exact live state',
        metrics=['per-trial decision/rejection counts','longest passing continuous run','record integrity'],
        no_fitting=True, no_accuracy_claim=True, rest_gate_requires_independent_labels=True,
        split='No train/test fit this round. Do not split overlapping windows from one capture.'))
    client = connect()
    try:
        probe = """import pathlib,json
r=pathlib.Path(%r)
records=[]
for p in sorted((r/'recordings').glob('*/metadata.json')):
 try:m=json.loads(p.read_text())
 except (OSError,ValueError):continue
 if m.get('task')=='ssvep' and m.get('state') in ('complete','duration_limit','service_stopped'):
  records.append(dict(id=p.parent.name,metadata=m))
print(json.dumps(records))
""" % PROD
        inventory = json.loads(command(client,PYTHON+' -c '+shlex.quote(probe)))
        dump(OUT/'inventory.json',inventory)
        (OUT/'runtime').mkdir()
        (OUT/'recordings').mkdir()
        with client.open_sftp() as sftp:
            for name in ('ssvep_cued_trials.jsonl','ssvep_free_events.jsonl','release_manifest.json'):
                sftp.get(PROD+'/'+name,str(OUT/name))
            manifest = json.loads((OUT/'release_manifest.json').read_text())
            for name in ('ssvep_stream.py','ssvep_core.py','ssvep_shadow.py','ssvep_cued.py',
                         'cyton_sqi.py','cyton_trial_recorder.py','ssvep_causal_protocol.json',
                         'ssvep_candidate_sos.npy'):
                sftp.get(PROD+'/'+name,str(OUT/'runtime'/name))
                if digest(OUT/'runtime'/name) != manifest['files'][name]:
                    raise ValueError('Installed runtime hash mismatch: '+name)
            for row in inventory:
                token=row['id']
                if not re.fullmatch('[0-9a-f]{16}',token):raise ValueError('Unexpected recording ID')
                folder=OUT/'recordings'/token;folder.mkdir()
                for name in FILES:sftp.get(PROD+'/recordings/'+token+'/'+name,str(folder/name))
        dump(OUT/'collected.json',dict(recordings=len(inventory),
            release_id=manifest['release_id'],
            sha256={str(p.relative_to(OUT)):digest(p) for p in OUT.rglob('*') if p.is_file()},
            board_writes=False))
        print('COLLECTED',len(inventory),'closed SSVEP recordings; board unchanged',flush=True)
    finally:client.close()


def audit_capture(folder):
    meta=json.loads((folder/'metadata.json').read_text())
    if meta['channel_map']!=CAP or meta['sample_rate_hz']!=250:
        raise ValueError('Fixed-cap/sample rate mismatch')
    n=meta['samples']
    expected={'samples_i32le.bin':32*n,'sequence_u8.bin':n,'flags_u8.bin':n,
              'stream_index_u64le.bin':8*n,'arrival_mono_f64le.bin':8*n}
    if n<=0 or any((folder/name).stat().st_size!=size for name,size in expected.items()):
        raise ValueError('Incomplete raw capture: '+folder.name)
    adc=np.fromfile(folder/'samples_i32le.bin',dtype='<i4').reshape(-1,8)
    times=np.fromfile(folder/'arrival_mono_f64le.bin',dtype='<f8')
    indices=np.fromfile(folder/'stream_index_u64le.bin',dtype='<u8')
    sequence=np.fromfile(folder/'sequence_u8.bin',dtype='u1')
    flags=np.fromfile(folder/'flags_u8.bin',dtype='u1')
    if not np.isfinite(times).all() or (times<0).any() or (np.diff(times)<0).any():
        raise ValueError('Invalid receive timestamps')
    if np.any(indices[1:]!=indices[:-1]+1):raise ValueError('Non-contiguous service indices')
    gap=((sequence[1:].astype(int)-sequence[:-1].astype(int))%256)!=1
    if not np.array_equal(gap,(flags[1:]&1)!=0):raise ValueError('Sequence flags disagree')
    return meta,adc,times,flags


def analyze():
    ledger=json.loads((OUT/'collected.json').read_text())
    for name,checksum in ledger['sha256'].items():
        if digest(OUT/name)!=checksum:raise ValueError('Collected artifact changed: '+name)
    sys.path.insert(0,str(OUT/'runtime'))
    from ssvep_stream import SSVEPStream
    from cyton_sqi import channel_sqi
    config=json.loads((OUT/'runtime/ssvep_causal_protocol.json').read_text())
    sos=np.load(OUT/'runtime/ssvep_candidate_sos.npy',allow_pickle=False)
    cue=[json.loads(line) for line in (OUT/'ssvep_cued_trials.jsonl').read_text().splitlines()]
    free=[json.loads(line) for line in (OUT/'ssvep_free_events.jsonl').read_text().splitlines()]
    summaries=[];replay_rows=[]
    for folder in sorted((OUT/'recordings').iterdir()):
        try:meta,adc,times,flags=audit_capture(folder)
        except ValueError as exc:
            summaries.append(dict(recording_id=folder.name,integrity=False,error=str(exc)));continue
        linked=[r for r in cue if r.get('raw_recording_id')==folder.name]
        trials=[]
        for start in (r for r in linked if r.get('event')=='trial_start'):
            rows=[r for r in linked if r.get('trial_id')==start['trial_id']]
            marks=[r for r in rows if r.get('event')=='presentation_receipt']
            ends=[r for r in rows if r.get('event')=='trial_end']
            if len(marks)!=1 or len(ends)!=1:continue
            if any(r.get('board_boot_id')!=meta['board_boot_id'] for r in rows):
                raise ValueError('Raw/cue boot mismatch')
            onset=marks[0]['board_monotonic_s'];end=ends[0]['board_monotonic_s']
            trials.append(dict(trial_id=start['trial_id'],target_hz=start['target_hz'],
                onset=onset,end=end,ever_matched=ends[0]['ever_matched'],
                raw_coverage=bool(times[0]<=onset<end<=times[-1])))
        stream=SSVEPStream(config,sos)
        values=adc.astype(float)*meta['microvolts_per_count']
        filtered=np.empty((len(adc),2));valid_filter=np.zeros(len(adc),bool)
        reset=(flags&3)!=0
        rails=np.any(np.abs(adc[:,6:8].astype(np.int64))>=8388607*.99,axis=1)
        reset[1:]|=(np.diff(times)>.25)|rails[:-1]
        reset|=rails;reset[0]=True
        events=[]
        # Exact frozen batching within each uninterrupted segment, not a live-state reconstruction.
        boundaries=list(np.flatnonzero(reset))+[len(adc)]
        for a,b in zip(boundaries,boundaries[1:]):
            stream.reset('capture_or_gap')
            if rails[a] or flags[a]&2:a+=1
            for i in range(a,b-9,10):
                events.extend(stream.push(values[i:i+10],i))
                filtered[i:i+10]=stream.last_filtered;valid_filter[i:i+10]=True
        for trial in trials:
            counts=Counter();winners=Counter();pass_run=longest=0;last=None;previous_hz=None
            emitted=[]
            for e in events:
                start,end_idx=e['window_start_index'],e['window_end_index_exclusive']
                received=times[end_idx-1]
                if not trial['onset']+2.5<=received<=trial['end']:continue
                reason=[];scores=e['scores']
                if not valid_filter[start:end_idx].all():reason.append('filter_reset')
                else:
                    x=np.zeros((end_idx-start,8))
                    x[:,:2]=values[start:end_idx,6:8]
                    x[:,2:4]=filtered[start:end_idx]
                    q=channel_sqi(x,channel_indices=(0,1,2,3))
                    if np.any(q[:,2]>=.95) or np.any(q[2:,1]>100):reason.append('hard_quality')
                if scores is None:reason.append('invalid_scores');winner=None;score=margin=None
                else:
                    ranked=np.argsort(scores);winner=config['frequencies_hz'][ranked[-1]]
                    score=scores[ranked[-1]];margin=score-scores[ranked[-2]]
                    if score<.55:reason.append('score_below_minimum')
                    if margin<.10:reason.append('margin_below_minimum')
                    winners[str(winner)]+=1
                counts.update(reason or ['passing_window'])
                if not reason and last is not None and end_idx-last==50 and winner==previous_hz:
                    pass_run+=1
                else:pass_run=1 if not reason else 0
                longest=max(longest,pass_run);last=end_idx;previous_hz=winner
                emitted.append(dict(end_row=end_idx,received_monotonic=received,winner=winner,
                    score=score,margin=margin,failures=reason))
            target=trial['target_hz']
            trialsum=dict(trial, windows=len(emitted),winner_counts=dict(winners),
                failure_counts=dict(counts),longest_passing_continuous_hops=longest,
                frozen_free_confirm_possible=longest>=11,
                rest_label_means_requested_no_flicker_not_verified_gaze=target==0)
            trials[trials.index(trial)]=trialsum
            replay_rows.append(dict(recording_id=folder.name,trial_id=trial['trial_id'],windows=emitted))
        summaries.append(dict(recording_id=folder.name,integrity=True,samples=len(adc),
            gaps=int(np.count_nonzero(flags&1)),malformed=int(np.count_nonzero(flags&2)),
            rail_rows=int(rails.sum()),trials=trials))
    recent=[]
    for start in [r for r in free if r.get('event')=='start'][-12:]:
        rows=[r for r in free if r.get('id')==start['id']]
        d=[r for r in rows if r.get('event')=='window_diagnostic']
        if not d:continue
        recent.append(dict(id=start['id'],frequencies=start['frequencies'],windows=len(d),
            reasons=dict(Counter(r['reason'] for r in d)),
            failures=dict(Counter(f for r in d for f in (r.get('decision') or {}).get('failures',[]))),
            confirmed_windows=sum(r.get('accepted') is True for r in d),
            raw_recording_linked=False,intended_gaze_label_available=False))
    report=dict(created_at=datetime.now().astimezone().isoformat(),recordings=summaries,
        recent_free_sessions=recent,script_sha256=digest(Path(__file__)),
        thresholds_fitted=False,thresholds_deployed=False,
        limitations=['Fresh filter state at raw capture boundary differs from uninterrupted live state.',
            'Single wearer; requested cue is not verified gaze or optical onset.',
            'Free sessions lack raw recording linkage and intended-gaze/rest labels.',
            'No independent rest holdout for calibrating a new controller threshold.',
            'Overlapping windows are diagnostics, not independent accuracy trials.'],
        recognition_accuracy_claimed=False,physical_control_enabled=False)
    dump(OUT/'analysis.json',report);dump(OUT/'replay_windows.json',replay_rows)
    print(json.dumps(dict(recordings=len(summaries),trials=sum(len(r.get('trials',[])) for r in summaries),
        free_sessions=len(recent),thresholds_changed=False),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('collect','analyze'))
    args=parser.parse_args()
    globals()[args.action]()

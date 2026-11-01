"""Read-only export and numerical audit of a completed live MI personal session."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shlex
import sys

import numpy as np

from run_soak_stage import connect, command
from run_mi_arm_acceptance import digest, dump, snapshot

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT/'eeg_apps_z15/output/mi_personal_live_20261003'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', default='study-477453603fea5cdd')
    parser.add_argument('--output', type=Path,
                        default=ROOT/'eeg_apps_z15/output/mi_personal_confirmation_20261003')
    args = parser.parse_args()
    if not args.study.startswith('study-') or any(c not in 'study-0123456789abcdef' for c in args.study):
        raise ValueError('Unexpected study directory')
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    data = out/'records'
    data.mkdir()
    deployment = load(DEPLOYMENT/'audit.json')
    remote = deployment['remote_directory']+'/'+args.study
    audit = dict(started_at=datetime.now().astimezone().isoformat(),
                 remote_directory=remote, source='live', passed=False,
                 accuracy_scope='one_wearer_one_session_intended_cue_labels',
                 board_modified=False, model_promoted=False, control_enabled=False)
    audit['audit_script_sha256'] = digest(Path(__file__))
    audit['candidate_stage_sha256'] = deployment['stage_sha256']
    client = connect()
    try:
        with client.open_sftp() as sftp:
            for name, expected in deployment['stage_sha256'].items():
                actual = command(client, 'sha256sum '+shlex.quote(deployment['remote_directory']+'/'+name)).split()[0]
                if actual != expected or digest(DEPLOYMENT/'stage'/name) != expected:
                    raise ValueError('Candidate source/weights changed: '+name)
            for name in ('manifest.json', 'events.jsonl', 'personal_readout.npz'):
                sftp.get(remote+'/'+name, str(data/name))
            records = {}
            for phase in ('calibration','confirmation'):
                (data/phase).mkdir()
                for name in ('report.json','plan.json','trials.json'):
                    sftp.get(remote+'/'+phase+'/'+name,str(data/phase/name))
                rows = load(data/phase/'trials.json')
                if len(rows) != 12 or [r['ordinal'] for r in rows] != list(range(1,13)):
                    raise ValueError('Missing or repeated trials')
                records[phase] = rows
                for row in rows:
                    expected_path = phase+'/trial-%02d.npz' % row['ordinal']
                    if row['array_file'] != expected_path:
                        raise ValueError('Unexpected trial path')
                    sftp.get(remote+'/'+expected_path, str(data/expected_path))
                    if digest(data/expected_path) != row['sha256']:
                        raise ValueError('Trial checksum mismatch')
        protected = snapshot(client)
        audit['formal_hashes_unchanged'] = protected['hashes'] == deployment['runtime_before']['hashes']
        audit['service_snapshot'] = protected['services']
        if not audit['formal_hashes_unchanged']:
            raise ValueError('Protected formal artifacts changed')
    finally:
        client.close()
    manifest = load(data/'manifest.json')
    if (manifest['source'] != 'live' or manifest['channels'] != ['F3','F4','C3','C4','T7','T8','O1','O2']
            or manifest['control_enabled'] is not False):
        raise ValueError('Session identity mismatch')
    events = [json.loads(line) for line in (data/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    completed = [e for e in events if e['event']=='study_block_complete']
    begins = [e for e in events if e['event']=='study_begin']
    if ([e['phase'] for e in completed] != ['calibration','confirmation']
            or [e['phase'] for e in begins] != ['calibration','confirmation']
            or completed[0]['monotonic_s'] >= begins[1]['monotonic_s']):
        raise ValueError('Calibration/confirmation timeline invalid')
    if any(e['event']=='virtual_command' for e in events):
        raise ValueError('Unexpected virtual actuation')
    frozen_sha = load(data/'calibration/report.json')['readout_sha256']
    if digest(data/'personal_readout.npz') != frozen_sha or completed[0]['readout_sha256'] != frozen_sha:
        raise ValueError('Readout changed since calibration finished')
    sys.path.insert(0,str(DEPLOYMENT/'stage'))
    from mi_eegnet_rms import OfflineEEGNet
    from mi_personal_study import PersonalReadout
    from mi_cued import hard_invalid
    base = OfflineEEGNet(DEPLOYMENT/'stage/experimental_rms_eegnet.npz',allow_experimental=True)
    matrices, predictions, windows, times, ids = {}, {}, [], [], []
    packet_intervals = []
    max_errors = dict(features=0., source_logits=0., personal_logits=0., fit_parameters=0.)
    for phase in ('calibration','confirmation'):
        rows = records[phase]
        plan = load(data/phase/'plan.json')
        if [r['target'] for r in rows] != plan['order']:
            raise ValueError('Cue order differs from prespecified plan')
        expected = np.random.default_rng(20261003 if phase=='calibration' else 20261004).permutation(
            ['left']*6+['right']*6).tolist()
        if plan['order'] != expected:
            raise ValueError('Cue order seed mismatch')
        features, labels, results = [], [], []
        for row in rows:
            ids.append(row['id'])
            times.append((row['start_monotonic'],row['end_monotonic']))
            with np.load(data/row['array_file'],allow_pickle=False) as a:
                metadata = json.loads(str(a['metadata'].item()))
                if any(metadata[key] != value for key,value in row.items() if key not in ('array_file','sha256')):
                    raise ValueError('Saved trial metadata mismatch')
                if (a['sensor_uv'].ndim!=2 or a['sensor_uv'].shape[1]!=8
                        or len(a['sensor_uv']) != len(a['sequences'])
                        or not np.isfinite(a['sensor_uv']).all()
                        or not np.array_equal((a['sequences'][:-1]+1)%256,a['sequences'][1:])):
                    raise ValueError('Raw trace or packet continuity mismatch')
                stamps, lengths = a['batch_received_monotonic'], a['batch_lengths']
                if (len(stamps)!=len(lengths) or sum(lengths)!=len(a['sensor_uv'])
                        or np.any(np.diff(stamps)<=0) or np.any(lengths<=0)):
                    raise ValueError('Packet batch timestamps invalid')
                packet_intervals.append((float(stamps[0]-(lengths[0]-1)/250),float(stamps[-1])))
                if not row['accepted']:
                    results.append(dict(id=row['id'],target=row['target'],accepted=False,reason=row['reason']))
                    continue
                if a['conditioned_uv'].shape!=(500,8) or hard_invalid(a['conditioned_uv']):
                    raise ValueError('Accepted window violates unchanged hard SQI')
                wave = a['filtered'].T[None]
                f = base.features(wave)[0]
                logits = base.score_features(f[None])[0]
                np.testing.assert_allclose(f,a['features'],rtol=1e-7,atol=1e-7)
                np.testing.assert_allclose(logits,a['source_logits'],rtol=0,atol=1e-5)
                max_errors['features'] = max(max_errors['features'],float(np.max(np.abs(f-a['features']))))
                max_errors['source_logits'] = max(max_errors['source_logits'],float(np.max(np.abs(logits-a['source_logits']))))
                candidate_logit = a['logits'].copy()
                label = ('left','right')[int(np.argmax(candidate_logit))]
                source_label = ('left','right')[int(np.argmax(logits))]
                if row['result']['label']!=label or row['source_label']!=source_label:
                    raise ValueError('Class interpretation mismatch')
                np.testing.assert_allclose(candidate_logit,row['result']['logits'],rtol=0,atol=1e-10)
                start,end = row['result']['window_start'],row['result']['window_end_exclusive']
                if end-start!=500:
                    raise ValueError('Unexpected MI window length')
                relative_start = start-int(a['sensor_first_stream_index'])
                if relative_start<125 or relative_start+500>len(a['sensor_uv']):
                    raise ValueError('Model window not contained in the saved trial trace')
                windows.append((start,end))
                features.append(f)
                labels.append(-1 if row['target']=='left' else 1)
                results.append(dict(id=row['id'], target=row['target'], accepted=True, label=label,
                                    source_label=source_label, logits=candidate_logit.tolist(),
                                    source_logits=logits.tolist()))
        matrices[phase] = (np.stack(features),np.array(labels))
        predictions[phase] = results
    if len(set(ids))!=24 or any(a[1]>=b[0] for a,b in zip(times,times[1:])):
        raise ValueError('Repeated trial IDs or overlapping trial times')
    resets = []
    for i,(a,b) in enumerate(zip(windows,windows[1:])):
        if a[1]>b[0]:
            between = [e for e in events if e['event']=='withdraw'
                       and times[i][1] <= e['monotonic_s'] <= times[i+1][0]]
            if not between:
                raise ValueError('Model indices overlap without a documented between-trial stream reset')
            resets.append(dict(after_trial=ids[i],before_trial=ids[i+1],events=between))
    if any(a[1]>=b[0] for a,b in zip(packet_intervals,packet_intervals[1:])):
        raise ValueError('Saved packet timestamp ranges overlap')
    personal = PersonalReadout()
    personal.fit(*matrices['calibration'])
    with np.load(data/'personal_readout.npz',allow_pickle=False) as frozen:
        for key,value in personal.arrays().items():
            np.testing.assert_allclose(value,frozen[key],rtol=1e-7,atol=1e-8)
            max_errors['fit_parameters'] = max(max_errors['fit_parameters'],float(np.max(np.abs(value-frozen[key]))))
    test_logits = personal.logits(matrices['confirmation'][0])
    for logits,row in zip(test_logits,[r for r in predictions['confirmation'] if r['accepted']]):
        np.testing.assert_allclose(logits,row['logits'],rtol=0,atol=1e-5)
        max_errors['personal_logits'] = max(max_errors['personal_logits'],float(np.max(np.abs(logits-row['logits']))))
    test = predictions['confirmation']
    metrics = {}
    for name,key in (('rms_base','source_label'),('personal_ridge','label')):
        valid = [r for r in test if r['accepted']]
        correct = sum(r[key]==r['target'] for r in valid)
        metrics[name] = dict(attempted=12,accepted=len(valid),rejected=12-len(valid),correct=correct,
                            accuracy_all_attempts=correct/12,
                            confusion={c:{p:sum(r['target']==c and (r[key] if r['accepted'] else 'rejected')==p
                              for r in test) for p in ('left','right','rejected')} for c in ('left','right')},
                            predicted_counts=dict(Counter(r[key] for r in valid)))
    summary = load(data/'confirmation/report.json')
    if (summary['correct_all_attempts'] != metrics['personal_ridge']['correct']
            or summary['source_correct_all_attempts'] != metrics['rms_base']['correct']):
        raise ValueError('Online headline differs from trial-level calculation')
    wins = sum(r['label']==r['target'] and r['source_label']!=r['target'] for r in test if r['accepted'])
    losses = sum(r['source_label']==r['target'] and r['label']!=r['target'] for r in test if r['accepted'])
    audit.update(passed=True, fixed_channels=manifest['channels'], frozen_readout_sha256=frozen_sha,
                 calibration_counts=dict(Counter(r['target'] for r in records['calibration'] if r['accepted'])),
                 metrics=metrics, personal_only_correct=wins, base_only_correct=losses,
                 max_numerical_errors=max_errors, parameters_refit_from_calibration_only=True,
                 confirmation_parameters_unchanged=True, windows_and_trials_nonoverlapping=True,
                 between_trial_stream_resets=resets,
                 decision='do_not_promote_personal_readout_no_improvement',
                 full_raw_continuous_filter_replay_verified=False,
                 limitation='Intertrial raw data/filter initial state not saved; verified saved-window feature/readout path only')
    dump(out/'predictions.json',predictions)
    dump(out/'audit.json',audit)
    dump(out/'SHA256.json',{str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps({key:audit[key] for key in ('passed','metrics','personal_only_correct','base_only_correct',
          'max_numerical_errors','decision')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

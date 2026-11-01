"""Audit cued-SSVEP logging with old replay events and explicit synthetic faults.

Historical Cyton events retain source='replay' and can never count as live
attention. The synthetic branch exercises the interlock only, not EEG accuracy.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'pynq_guardianloop'))
from ssvep_cued import CuedSSVEPSession  # noqa: E402


class Clock:
    def __init__(self, value=100.):
        self.value = value

    def __call__(self):
        return self.value


def command(cue, token, action, **fields):
    return cue.command(dict(action=action, id=token, **fields))


def present(cue, target):
    trial = cue.command(dict(action='start', target_hz=target))
    token = trial['id']
    command(cue, token, 'presented', browser_onset_ms=500., browser_send_ms=501.)
    return token


def heartbeat(cue, token, clock, target):
    return command(cue, token, 'heartbeat', frame_count=180,
                   duration_ms=3000, max_gap_ms=17,
                   poor_frames=0, display_hz=target)


def live(clock, end, frequency=10., state='candidate_only', stale=False):
    row = dict(source='live', state=state, valid=state=='candidate_only',
               frequency_hz=frequency if state=='candidate_only' else None,
               window_start_index=end-500 if end is not None else None,
               window_end_index_exclusive=end, input_age_seconds=0.,
               updated_monotonic=clock.value, packets_seen=end,
               sequence_gaps=0, quality={'hard_bad':state!='candidate_only'})
    return dict(live=row, stale=stale)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recorded-events', type=Path, default=ROOT/'eeg_apps_z15/output/ssvep_shadow_20260927/replay_events.json')
    parser.add_argument('--output', type=Path, default=ROOT/'eeg_apps_z15/output/ssvep_cued_audit_20260930')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    recorded_bytes = args.recorded_events.read_bytes()
    recorded = json.loads(recorded_bytes)
    if not isinstance(recorded, list) or not all(row.get('source')=='replay' for row in recorded):
        raise ValueError('Expected preserved replay-source Cyton shadow events')

    clock = Clock()
    cue = CuedSSVEPSession(clock, args.output/'recorded_replay_trials.jsonl')
    recorded_checks = []
    for segment in (recorded[:15], recorded[42:57]):
        token = present(cue, 10.)
        clock.value += 2.6
        heartbeat(cue, token, clock, 10.)
        for event in segment:
            # Only scheduling time is replaced for this deterministic replay.
            # The EEG source, quality and candidate values remain historical.
            event = dict(event, updated_monotonic=clock.value,
                         input_age_seconds=0.)
            result = cue.observe(dict(live=event, stale=False))
            recorded_checks.append(result['accepted'])
            clock.value += .2
            if int((clock.value*10)) % 4 == 0:
                heartbeat(cue, token, clock, 10.)
        command(cue, token, 'stop')
        clock.value += .1
    assert len(recorded_checks)==30 and not any(recorded_checks)

    clock = Clock(500.)
    cue = CuedSSVEPSession(clock, args.output/'synthetic_interlock_trials.jsonl')
    token = present(cue, 10.)
    clock.value += 2.6
    heartbeat(cue, token, clock, 10.)
    first = []
    for end in (700,750,800):
        first.append(cue.observe(live(clock,end))['accepted'])
        clock.value += .2
    assert first == [False,False,True]
    revoked = cue.observe(live(clock,850,stale=True))
    assert not revoked['accepted']
    clock.value += .2
    no_data = cue.observe(live(clock,None,state='no_data'))
    assert not no_data['accepted']
    recovered = []
    for end in (1360,1410,1460):
        clock.value += .2
        heartbeat(cue, token, clock, 10.)
        recovered.append(cue.observe(live(clock,end))['accepted'])
    assert recovered == [False,False,True]
    command(cue, token, 'stop')
    rest_token = present(cue, 0.)
    clock.value += 2.6
    heartbeat(cue, rest_token, clock, 0.)
    rest = cue.observe(live(clock,1510))
    assert not rest['accepted'] and rest['reason']=='rest_no_control'
    command(cue, rest_token, 'stop')

    report = dict(recorded=dict(source='historical_cyton_replay',
                                input_sha256=hashlib.sha256(recorded_bytes).hexdigest(),
                                inspected_snapshots=len(recorded_checks),
                                accepted_snapshots=sum(recorded_checks),
                                note='Replay source remains replay. No stimulus or accuracy label was added.'),
                  synthetic=dict(source='fabricated_interlock_inputs_not_EEG',
                                 initial_match=first, revoked_on_stale=not revoked['accepted'],
                                 no_data_rejected=not no_data['accepted'],
                                 reaccepted_after_fresh_windows=recovered,
                                 rest_candidate_rejected=not rest['accepted']),
                  audit_schema='ssvep-cued-trial-v1',
                  source_sha256=hashlib.sha256((ROOT/'pynq_guardianloop/ssvep_cued.py').read_bytes()).hexdigest(),
                  limitation='Neither recorded replay nor synthetic inputs validate optical flicker, gaze accuracy or real no-target false-trigger rate.')
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False,
                                                  indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

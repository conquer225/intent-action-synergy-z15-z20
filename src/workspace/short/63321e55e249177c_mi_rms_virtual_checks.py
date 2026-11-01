"""Checks for the isolated shared-RMS replay/virtual server, never accuracy scoring."""
import argparse
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

from mi_cued_acceptance import logical_replay
from mi_cued_replay import load_recording
from mi_eegnet_rms import OfflineEEGNet


def request(base, body=None):
    req = Request(base+'/api/mi-cue', data=json.dumps(body).encode() if body else None,
                  headers={'Origin':base,'Content-Type':'application/json'})
    with urlopen(req, timeout=3) as response:
        return json.load(response)


def wait_state(base, predicate, limit=5, trial=None):
    deadline = time.monotonic()+limit
    while time.monotonic()<deadline:
        state = request(base, dict(action='heartbeat', id=trial) if trial else None)
        if predicate(state):
            return state
        time.sleep(.15)
    raise TimeoutError('Expected replay state not reached')


def functional(model, raw, seq, output):
    summaries = []
    for enabled, name in ((False, 'observe'), (True, 'virtual')):
        path = output/name
        path.mkdir()
        summaries.append(logical_replay(model, raw, seq, path, virtual_control=enabled))
    with np.load(output/'observe/arrays.npz') as a, np.load(output/'virtual/arrays.npz') as b:
        identical = all(np.array_equal(a[key], b[key], equal_nan=True)
                        for key in ('conditioned','filtered','valid','logits'))
    events = [json.loads(line) for line in (output/'virtual/events.jsonl').read_text().splitlines()]
    commands = [event for event in events if event['event']=='virtual_command']
    checks = dict(filters_and_logits_exact=identical, observe_no_commands=summaries[0]['virtual_commands']==0,
                  one_command_per_prediction=len(commands)==summaries[1]['candidates']==13,
                  unique_trials=len({event['trial_id'] for event in commands})==len(commands),
                  bounded_position=all(0<=event['position_after']<=100 for event in commands),
                  follows_model_not_cue=all(event['action']==('open_step' if event['label']=='left' else 'close_step')
                                           for event in commands),
                  never_physical=all(event['simulation'] and not event['control_enabled']
                                     and event['source']=='replay' for event in commands),
                  eof_withdrawn=all(summary['eof_withdrawn'] and summary['virtual_stopped'] for summary in summaries))
    return dict(checks=checks, summaries=summaries, passed=all(checks.values()), accuracy_scored=False)


def http_checks(base):
    checks = {}
    snapshots = {}
    request(base, dict(action='replay_stop'))
    idle = request(base)
    checks['explicit_replay_unpromoted'] = (idle['source']=='replay' and not idle['production_eligible']
                                            and not idle['control_enabled'] and not idle['replay']['auto_repeat'])
    try:
        request(base, dict(action='start', target='left', virtual_control=True))
    except HTTPError as error:
        checks['no_data_start_refused'] = error.code==400
    else:
        checks['no_data_start_refused'] = False
    request(base, dict(action='replay_start'))
    try:
        ready = wait_state(base, lambda state:state['input_state']=='ready')
        start = request(base, dict(action='start', target='left', virtual_control=True))
        trial = start['id']
        request(base, dict(action='presented', id=trial, browser_onset_ms=1, browser_send_ms=2))
        predicted = wait_state(base, lambda state:state['result'] is not None, trial=trial)
        command = predicted['virtual_hand']['last_command']
        checks['model_drives_one_command'] = bool(command and command['trial_id']==trial
            and command['label']==predicted['result']['label']
            and command['action']==('open_step' if command['label']=='left' else 'close_step'))
        count = predicted['virtual_hand']['command_count']
        for _ in range(4):
            state = request(base, dict(action='heartbeat', id=trial))
            time.sleep(.15)
        checks['polling_does_not_repeat'] = state['virtual_hand']['command_count']==count
        stopped = request(base, dict(action='stop', id=trial, reason='page_hidden'))
        checks['hidden_withdraws_keeps_pose'] = (stopped['result'] is None
            and not stopped['virtual_hand']['enabled'] and stopped['virtual_hand']['last_command'] is None
            and stopped['virtual_hand']['position_percent']==predicted['virtual_hand']['position_percent'])
        rest = request(base, dict(action='start', target='rest', virtual_control=True))
        trial = rest['id']
        request(base, dict(action='presented', id=trial, browser_onset_ms=1, browser_send_ms=2))
        for _ in range(18):
            time.sleep(.15)
            rest = request(base, dict(action='heartbeat', id=trial))
        checks['rest_disarms_no_prediction'] = (rest['result'] is None and not rest['virtual_hand']['enabled']
                                                and rest['virtual_hand']['command_count']==count)
        request(base, dict(action='replay_stop'))
        stop = request(base)
        checks['stop_resets_and_withdraws'] = (stop['input_state']=='no_data' and stop['received_samples']==0
            and stop['result'] is None and not stop['virtual_hand']['enabled'])
        request(base, dict(action='replay_start'))
        rewarm = wait_state(base, lambda state:state['input_state']=='ready')
        checks['restart_rewarms_no_old_prediction'] = (rewarm['replay']['run']==ready['replay']['run']+1
            and rewarm['result'] is None and rewarm['virtual_hand']['last_command'] is None)
        snapshots.update(ready=ready, predicted=predicted, hidden=stopped, rest=rest, stopped=stop, rewarm=rewarm)
    finally:
        request(base, dict(action='replay_stop'))
    return dict(checks=checks, snapshots=snapshots, passed=all(checks.values()), accuracy_scored=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-url')
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    if args.base_url:
        report = http_checks(args.base_url)
    else:
        root = Path(__file__).resolve().parent
        raw, seq = load_recording(root/'bench_input.npz')
        model = OfflineEEGNet(root/'experimental_rms_eegnet.npz', allow_experimental=True)
        report = functional(model, raw, seq, args.output)
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                     allow_nan=False)+'\n', encoding='utf-8')
    print('RMS_VIRTUAL_CHECKS', json.dumps(report['checks']), flush=True)
    if not report['passed']:
        raise AssertionError('RMS virtual checks failed')


if __name__ == '__main__':
    main()

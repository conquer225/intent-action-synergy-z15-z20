"""Recorded-only virtual MI control parity; never reads serial or sends hardware commands."""
import argparse
import hashlib
import json
from pathlib import Path
import platform

import numpy as np

from mi_cued_acceptance import logical_replay
from mi_cued_replay import load_recording
from mi_eegnet_portable import OfflineEEGNet


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    raw, sequences = load_recording(args.input)
    model = OfflineEEGNet(args.model, allow_experimental=True)
    summaries, decisions = [], []
    for mode in ('observe', 'virtual'):
        directory = args.output / mode
        directory.mkdir()
        summaries.append(logical_replay(model, raw, sequences, directory,
                                        virtual_control=mode == 'virtual'))
        data = json.loads((directory / 'replay.json').read_text(encoding='utf-8'))
        decisions.append([(row['trial'], row['target'], row['label'], row['logits'],
                           row['window_start'], row['window_end_exclusive'])
                          for row in data['results']])
    with np.load(args.output / 'observe' / 'arrays.npz') as a, np.load(
            args.output / 'virtual' / 'arrays.npz') as b:
        filters_identical = all(np.array_equal(a[key], b[key], equal_nan=True)
                                for key in ('conditioned', 'filtered', 'valid', 'logits'))
    events = [json.loads(line) for line in (args.output / 'virtual' / 'events.jsonl').read_text(
        encoding='utf-8').splitlines()]
    commands = [event for event in events if event['event'] == 'virtual_command']
    mismatches = [event for event in events if event['event'] == 'candidate' and not event['matches_cue']]
    checks = dict(filters_and_logits_identical=filters_identical,
                  candidates_identical=decisions[0] == decisions[1],
                  observation_sends_no_virtual_commands=summaries[0]['virtual_commands'] == 0,
                  exactly_one_command_per_candidate=len(commands) == summaries[1]['candidates'],
                  unique_trials=len(set(event['trial_id'] for event in commands)) == len(commands),
                  bounded_position=all(0 <= event['position_after'] <= 100 for event in commands),
                  follows_model_not_cue=all(event['action'] == (
                      'open_step' if event['label'] == 'left' else 'close_step') for event in commands),
                  replay_no_hardware=all(event['source'] == 'replay' and event['simulation']
                                         and not event['control_enabled'] for event in commands),
                  eof_withdraws=all(summary['eof_withdrawn'] and summary['virtual_stopped']
                                   for summary in summaries))
    report = dict(checks=checks, passed=all(checks.values()), summaries=summaries,
                  mismatch_candidates=len(mismatches), python=platform.python_version(),
                  platform=platform.platform(), input=str(args.input), input_sha256=digest(args.input),
                  model_sha256=digest(args.model), samples=len(raw), source='replay',
                  accuracy_scored=False, production_eligible=False, control_enabled=False)
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                      allow_nan=False) + '\n', encoding='utf-8')
    print('MI_VIRTUAL_PARITY', json.dumps(report, ensure_ascii=False), flush=True)
    if not report['passed']:
        raise AssertionError('Virtual control changed MI computation or violated command policy')


if __name__ == '__main__':
    main()

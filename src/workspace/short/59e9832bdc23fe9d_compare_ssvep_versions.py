"""Compare recorded SSVEP decisions from the staged board version and cached candidate."""

import importlib.util
import json
import os
from pathlib import Path
import sys

import numpy as np


APP = Path(__file__).resolve().parents[1]
SNAPSHOT = APP / 'output' / 'pl_integrated_candidate_20260929'
sys.path.insert(0, str(APP))
from ssvep_stream import SSVEPStream as CachedStream  # noqa: E402


def load_board_stream():
    old_core = importlib.util.spec_from_file_location(
        'ssvep_core', SNAPSHOT / 'board_ssvep_core.py')
    core = importlib.util.module_from_spec(old_core)
    previous = sys.modules.get('ssvep_core')
    sys.modules['ssvep_core'] = core
    try:
        old_core.loader.exec_module(core)
        old_stream = importlib.util.spec_from_file_location(
            'board_ssvep_stream', SNAPSHOT / 'board_ssvep_stream.py')
        stream = importlib.util.module_from_spec(old_stream)
        old_stream.loader.exec_module(stream)
        return stream.SSVEPStream
    finally:
        if previous is None:
            del sys.modules['ssvep_core']
        else:
            sys.modules['ssvep_core'] = previous


def main():
    config = json.loads((SNAPSHOT / 'recorded_ssvep_causal_protocol.json').read_text())
    sos = np.load(SNAPSHOT / 'recorded_ssvep_candidate_sos.npy')
    old = load_board_stream()(config, sos)
    new = CachedStream(config, sos)
    with np.load(SNAPSHOT / 'recorded_input.npz') as record:
        samples = record['recorded'][:20000]
    max_score_diff = 0.
    events = 0
    cached_events = []
    for start in range(0, len(samples), 10):
        left = old.push(samples[start:start+10], start)
        right = new.push(samples[start:start+10], start)
        if len(left) != len(right):
            raise AssertionError(f'event count differs at {start}')
        for baseline, candidate in zip(left, right):
            cached_events.append(candidate)
            for field in ('status', 'window_start_index', 'window_end_index_exclusive',
                          'target_index', 'frequency_hz'):
                if baseline[field] != candidate[field]:
                    raise AssertionError(f'{field} differs at {start}: '
                                         f'{baseline[field]} vs {candidate[field]}')
            if baseline['scores'] is not None:
                delta = np.max(np.abs(np.asarray(baseline['scores']) - candidate['scores']))
                max_score_diff = max(max_score_diff, float(delta))
                if not np.allclose(baseline['scores'], candidate['scores'], atol=1e-6, rtol=1e-7):
                    raise AssertionError(f'scores differ at {start}: {delta}')
            events += 1
    rank2 = CachedStream(config, sos)
    rank2_events = []
    previous = os.environ.get('GUARDIANLOOP_EXPERIMENTAL_RANK2_CCA')
    os.environ['GUARDIANLOOP_EXPERIMENTAL_RANK2_CCA'] = '1'
    try:
        for start in range(0, len(samples), 10):
            rank2_events.extend(rank2.push(samples[start:start+10], start))
    finally:
        if previous is None:
            os.environ.pop('GUARDIANLOOP_EXPERIMENTAL_RANK2_CCA', None)
        else:
            os.environ['GUARDIANLOOP_EXPERIMENTAL_RANK2_CCA'] = previous
    if len(rank2_events) != len(cached_events):
        raise AssertionError('rank2 decision count differs')
    rank2_max_score_diff = 0.
    for cached, analytic in zip(cached_events, rank2_events):
        for field in ('status', 'window_start_index', 'window_end_index_exclusive',
                      'target_index', 'frequency_hz'):
            if cached[field] != analytic[field]:
                raise AssertionError(f'rank2 {field} differs')
        if cached['scores'] is not None:
            delta = np.max(np.abs(np.asarray(cached['scores']) - analytic['scores']))
            rank2_max_score_diff = max(rank2_max_score_diff, float(delta))
            if not np.allclose(cached['scores'], analytic['scores'], atol=1e-6, rtol=1e-7):
                raise AssertionError(f'rank2 scores differ: {delta}')
    print(json.dumps(dict(samples=len(samples), decisions=events,
                          max_score_abs_diff=max_score_diff,
                          rank2_max_score_abs_diff=rank2_max_score_diff,
                          all_states_targets_and_frequencies_equal=True,
                          board_old_decode_s=old.decode_seconds,
                          cached_decode_s=new.decode_seconds,
                          rank2_decode_s=rank2.decode_seconds)))


if __name__ == '__main__':
    main()

"""Compare isolated synchronous/async SEED replay events, not emotion accuracy."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path


def equivalent(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return (left.keys() == right.keys() and
                all(equivalent(left[key], right[key]) for key in left))
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            equivalent(a, b) for a, b in zip(left, right))
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        if isinstance(right, (int, float)) and not isinstance(right, bool):
            return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)
    return left == right


def load_events(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def equivalent_gap(left, right):
    if left is None or right is None:
        return left is None and right is None
    same_fields = equivalent({k: v for k, v in left.items() if k != 'seconds'},
                             {k: v for k, v in right.items() if k != 'seconds'})
    if 'seconds' not in left and 'seconds' not in right:
        return same_fields
    return (same_fields and 'seconds' in left and 'seconds' in right and
            .25 < left['seconds'] <= 5 and .25 < right['seconds'] <= 5 and
            abs(left['seconds'] - right['seconds']) < .1)


def compare(sync_path, async_path):
    sync = load_events(sync_path)
    async_events = load_events(async_path)
    mismatches = [index for index, (a, b) in enumerate(zip(sync, async_events))
                  if not equivalent(a['event'], b['event']) or
                  not equivalent_gap(a['last_gap'], b['last_gap']) or
                  a['sequence_gaps'] != b['sequence_gaps']]
    predictions = [item for item in async_events if item['event']['state'] == 'prediction']
    result = {
        'sync_event_counts': dict(Counter(item['event']['state'] for item in sync)),
        'async_event_counts': dict(Counter(item['event']['state'] for item in async_events)),
        'sync_event_count': len(sync), 'async_event_count': len(async_events),
        'mismatch_indices': mismatches,
        'async_valid_input_age_max_ms': max((item['input_age_ms'] for item in predictions),
                                        default=None),
        'sync_valid_input_age_max_ms': max((item['input_age_ms'] for item in sync
                    if item['event']['state'] == 'prediction'), default=None),
        'verdict': 'pass' if (len(sync) == len(async_events) and not mismatches and
                     len(predictions) >= 1 and
                     all(item['input_age_ms'] is not None and item['input_age_ms'] < 500
                         for item in predictions)) else 'fail',
        'scope': 'Same-input engineering replay event parity and candidate freshness only; '
                 'not SEED or wearer classification accuracy.',
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('sync_audit', type=Path)
    parser.add_argument('async_audit', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = compare(args.sync_audit, args.async_audit)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    if result['verdict'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()

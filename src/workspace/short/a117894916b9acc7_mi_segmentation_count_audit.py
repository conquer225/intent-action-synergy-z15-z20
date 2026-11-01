"""Audit improved/tied/declined counts with exact confusion-matrix fractions.

The locked run uses strict float signs. A round-off-sized delta must not be
reported as a changed participant outcome. Preserve that run; write an
independent descriptive correction without changing metrics or selection.
"""
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path


OUTPUT = Path(__file__).resolve().parent / 'output/mi_segmentation_20261001'


def exact_mean_ba(row):
    values = []
    if [r['seed'] for r in row['per_seed']] != [42, 43, 44]:
        raise ValueError('Seed identities changed')
    for seed in row['per_seed']:
        cm = seed['confusion_matrix']
        if len(cm) != 2 or any(len(r) != 2 for r in cm):
            raise ValueError('Binary confusion matrix required')
        if sum(map(sum, cm)) != row['trials'] or any(sum(r) == 0 for r in cm):
            raise ValueError('Trial/class counts changed')
        values.append((Fraction(cm[0][0], sum(cm[0])) +
                       Fraction(cm[1][1], sum(cm[1]))) / 2)
    return sum(values, Fraction(0)) / len(values)


def audit(output=OUTPUT):
    destination = output / 'count_audit.json'
    if destination.exists():
        raise RuntimeError('Existing descriptive correction preserved')
    results_path = output / 'results.json'
    raw = results_path.read_bytes()
    report = json.loads(raw)
    rows = []
    for candidate, reference in zip(report['candidate']['per_subject'],
                                    report['reference']['per_subject'], strict=True):
        if (candidate['subject'], candidate['trials']) != (reference['subject'], reference['trials']):
            raise ValueError('Paired people/trials differ')
        c, r = exact_mean_ba(candidate), exact_mean_ba(reference)
        for value, recorded in ((c, candidate['balanced_accuracy']),
                                 (r, reference['balanced_accuracy'])):
            if not math.isclose(float(value), recorded, rel_tol=0, abs_tol=1e-14):
                raise ValueError('Confusion-matrix metric does not match reported BA')
        delta = c - r
        rows.append({'subject': candidate['subject'], 'exact_ba_gain': str(delta),
                     'float_reported_ba_gain': candidate['balanced_accuracy'] - reference['balanced_accuracy'],
                     'outcome': 'improved' if delta > 0 else 'declined' if delta < 0 else 'tied'})
    counts = {name: sum(r['outcome'] == name for r in rows)
              for name in ('improved', 'declined', 'tied')}
    if sum(counts.values()) != 30:
        raise ValueError('Participant count changed')
    exact_gain = sum((Fraction(r['exact_ba_gain']) for r in rows), Fraction(0)) / len(rows)
    if not math.isclose(float(exact_gain), report['paired_comparison']['mean_ba_gain'], rel_tol=0, abs_tol=1e-14):
        raise ValueError('Mean gain differs beyond round-off')
    result = {'audit_passed': True, 'scope': 'Descriptive sign counts only; no fitting, protocol or gate change',
              'results_sha256': hashlib.sha256(raw).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'locked_float_counts': {name: report['paired_comparison']['people_' + name] for name in counts},
              'exact_fraction_counts': counts, 'exact_mean_ba_gain': str(exact_gain), 'per_subject': rows,
              'headline_metrics_changed': False, 'paired_ci_changed': False,
              'continuation_gate_passed': report['continuation_gate_passed'],
              'board_accessed': False, 'control_enabled': False}
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'exact_fraction_counts': counts, 'continuation_gate_passed': report['continuation_gate_passed']}, indent=2))


if __name__ == '__main__':
    audit()

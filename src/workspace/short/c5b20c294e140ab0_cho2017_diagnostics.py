"""Describe stored predictions; no raw confirmation data, classifier fits or new gates."""
import argparse
import json
from pathlib import Path

import numpy as np

from cho2017_data import hashes
from mi_spatial_development import metrics
from mi_physionet_evaluate import bootstrap_ci


def evaluate(rows):
    return metrics(np.array([r['label'] for r in rows]),
                   np.array([r['prediction'] for r in rows]),
                   np.array([r['subject'] for r in rows]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=Path(__file__).parent / 'output/cho2017_fixed8_dev_20261001')
    args = parser.parse_args()
    destination = args.run / 'diagnostics.json'
    if destination.exists():
        raise FileExistsError('Prior diagnostic preserved: ' + str(destination))
    report_path, prediction_path = args.run / 'development.json', args.run / 'predictions.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    stored = json.loads(prediction_path.read_text(encoding='utf-8'))
    protocol = report['protocol']
    people = set(protocol['development_subjects'])
    calibration_count = protocol['personal_calibration']['first_chronological_trials']
    methods = {}
    for name, predictions in stored.items():
        cross = predictions['cross']
        if set(r['subject'] for r in cross) != people:
            raise ValueError('Unexpected cross-development participants')
        clean = [r for r in cross if not (r['voltage_bad'] or r['emg_bad'])]
        later = [r for r in cross if r['original_order'] >= calibration_count]
        personal = [r for r in predictions['personal'] if r['subject'] in people]
        key = lambda row: (row['subject'], row['original_order'])
        later = sorted(later, key=key)
        personal = sorted(personal, key=key)
        if [(key(r), r['label']) for r in later] != [(key(r), r['label']) for r in personal]:
            raise ValueError('Personal and cross later-trial identities disagree')
        cross_later, personal_later = evaluate(later), evaluate(personal)
        paired = [b['balanced_accuracy'] - a['balanced_accuracy']
                  for a, b in zip(cross_later['per_subject'], personal_later['per_subject'])]
        methods[name] = {
            'clean_test_only_no_training_change': evaluate(clean),
            'clean_test_trials': len(clean), 'flagged_test_trials': len(cross) - len(clean),
            'cross_on_same_later_trials': cross_later,
            'personal_on_same_later_trials': personal_later,
            'paired_personal_minus_cross_mean': float(np.mean(paired)),
            'paired_subject_bootstrap_95_ci': bootstrap_ci(paired, protocol['seed']),
            'participants_improved': sum(v > 0 for v in paired),
            'participants_declined': sum(v < 0 for v in paired),
            'participants_unchanged': sum(v == 0 for v in paired),
        }
    output = {'scope': 'descriptive only; no classifier refitting, method selection, gate change or confirmation',
              'source_sha256': {str(p): hashes(p)['sha256'] for p in (report_path, prediction_path, Path(__file__))},
              'methods': methods,
              'limitations': ['clean-test diagnostic still uses the all-trial trained model',
                              'the development set is not an independent confirmation set',
                              'no causal proof that contamination or person shift alone explains errors']}
    destination.write_text(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    for name, result in methods.items():
        print(name, 'clean_test_BA', result['clean_test_only_no_training_change']['mean_subject_balanced_accuracy'],
              'same_later_cross_BA', result['cross_on_same_later_trials']['mean_subject_balanced_accuracy'],
              'personal_delta', result['paired_personal_minus_cross_mean'],
              'paired_CI', result['paired_subject_bootstrap_95_ci'], flush=True)


if __name__ == '__main__':
    main()

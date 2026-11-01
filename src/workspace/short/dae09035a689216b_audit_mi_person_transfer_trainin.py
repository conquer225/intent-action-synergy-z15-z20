"""Post-score training metadata audit; does not open EEG or fit a model."""
from collections import Counter
from datetime import datetime
from hashlib import sha256
from math import ceil
from pathlib import Path
from statistics import mean, median
import json

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_person_transfer_diagnostic_20261002'
ORIGINAL = HERE / 'output/mi_model_comparison_20261001'


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    target = RUN / 'training_metadata_audit.json'
    if target.exists():
        raise RuntimeError('Existing metadata audit preserved')
    lock = read(RUN / 'lock.json')
    frozen = read(RUN / 'source_freeze.json')
    for path, expected in {**lock['source_sha256'], **lock['input_sha256'], **frozen['files']}.items():
        assert digest(Path(path)) == expected, path
    config = read(HERE / 'mi_model_comparison_protocol.json')['eegnet']
    assert config['batch_size'] == 64 and config['bn_torch_momentum'] == .01
    counts = Counter(t['subject'] for t in read(ORIGINAL / 'trial_manifest.json'))
    folds = {f['target']: f for f in read(ORIGINAL / 'fold_manifest.json')}
    cases = read(RUN / 'case_manifest.json')
    groups = {method: [] for method in ('CROSS_ORIGINAL', 'PERSON_ONLY', 'CROSS_MATCHED80')}
    files = {}
    for case in cases:
        person, seed = case['person'], case['seed']
        for method in groups:
            if method == 'CROSS_ORIGINAL':
                path = ORIGINAL / 'network_checkpoints' / f's{person:02d}_seed{seed}.json'
                n_fit = sum(counts[p] for p in folds[person]['fit_people'])
            else:
                path = RUN / 'models' / f's{person:02d}_{method}_seed{seed}.json'
                n_fit = 80
                assert len(read(path)['fit_indices']) == n_fit
            metadata = read(path)
            history = metadata['history']
            best = max(h['source_validation_mean_person_ba'] for h in history)
            earliest = next(h['epoch'] for h in history if h['source_validation_mean_person_ba'] == best)
            assert metadata['best_epoch'] == earliest
            assert metadata['source_validation_mean_person_ba'] == best
            updates = ceil(n_fit / config['batch_size']) * earliest
            groups[method].append({
                'person': person, 'seed': seed, 'fit_trials': n_fit,
                'best_epoch': earliest, 'completed_epochs': metadata['completed_epochs'],
                'selected_validation_ba': best, 'updates_at_selected_checkpoint': updates,
                'theoretical_initial_BN_coefficient': (1 - config['bn_torch_momentum']) ** updates,
            })
            files[str(path)] = digest(path)
    summary = {}
    for method, rows in groups.items():
        assert len(rows) == 90
        summary[method] = {
            'fits': len(rows),
            'median_best_epoch': median(r['best_epoch'] for r in rows),
            'median_completed_epochs': median(r['completed_epochs'] for r in rows),
            'median_updates_at_selected_checkpoint': median(r['updates_at_selected_checkpoint'] for r in rows),
            'median_theoretical_initial_BN_coefficient': median(r['theoretical_initial_BN_coefficient'] for r in rows),
            'mean_selected_validation_ba': mean(r['selected_validation_ba'] for r in rows),
            'selected_validation_at_or_below_chance': sum(r['selected_validation_ba'] <= .5 for r in rows),
        }
    output = {
        'passed': True, 'scope': 'Post-score descriptive metadata; not a new fitted candidate or causal explanation',
        'models': summary, 'per_model': groups,
        'BN_coefficient_formula': '(1-momentum)**(ceil(fit_trials/batch_size)*selected_epoch)',
        'BN_coefficient_is_theoretical': True,
        'interpretation_limit': 'Coefficient quantifies initialization memory, not correctness or measured BN error; it cannot establish the cause of lower BA. No changed training or target recalibration.',
        'input_sha256': files, 'results_sha256': digest(RUN / 'results.json'),
        'script_sha256': digest(Path(__file__)), 'at_local': datetime.now().isoformat(),
        'model_fitted': False, 'new_eeg_forward': False, 'raw_mat_read': False, 'board_accessed': False,
    }
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

"""Pre-score source-BN-only control; unchanged old weights, no model selection."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil

from mi_crossfield_stability import (OUTPUT, read, digest, load, recalibrate_bn,
                                    frozen_models, integer_metrics)
from mi_model_comparison import HERE, fold_indices, save_prediction
from mi_comparison_models import EEGNetSmall, normalized_tensor, network_logits, configure_torch, torch
import numpy as np

NAME = 'ORIGINAL_BN_ONLY'


def prepare():
    p, old, stats, waves, folds = load(OUTPUT)
    if (OUTPUT/'target_access.json').exists():
        raise RuntimeError('This diagnostic must be frozen before ANY new target scoring')
    output = OUTPUT/'source_bn_diagnostic'
    output.mkdir(exist_ok=False)
    config = {'id': 'pre_score_original_BN_only_control', 'primary_candidate': False,
              'justification': 'Separate weight averaging from source-only BN recalibration;not a tuned competitor',
              'unchanged': 'All learned weights,biases,scalers,input,folds,seeds and old selected source epochs',
              'changed': 'BN running statistics only; same source-fit-only recalibration as main candidates',
              'target_selection': False, 'confirmation_eeg_read': False, 'no_refit': True,
              'source_file_sha256': digest(Path(__file__)), 'declared_at_local': datetime.now().isoformat()}
    (output/'protocol.json').write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    shutil.copy2(Path(__file__), output/Path(__file__).name)
    configure_torch(old['compute'])
    # Source-only CPU work does not alter the running GPU training process RNG.
    files = {}
    for fold in folds:
        fit, _, _ = fold_indices(stats['subjects'], stats['order'], fold)
        for seed in p['seeds']:
            original = HERE/p['original_run']/'network_checkpoints'/f's{fold["target"]:02d}_seed{seed}.pt'
            c = torch.load(original, map_location='cpu', weights_only=True)
            model = EEGNetSmall(c['config'])
            model.load_state_dict(c['state_dict'])
            before = {key: value.detach().clone() for key, value in model.named_parameters()}
            x = normalized_tensor(waves[fit], np.array(c['source_mean']), np.array(c['source_scale']), 'cpu')
            recalibrate_bn(model, x)
            for key, value in model.named_parameters():
                torch.testing.assert_close(value, before[key], rtol=0, atol=0)
            c['state_dict'] = {key: value.cpu() for key, value in model.state_dict().items()}
            c['diagnostic'] = {**fold, 'seed': seed, 'only_BN_buffers_changed': True}
            path = output/f's{fold["target"]:02d}_seed{seed}.pt'
            torch.save(c, path)
            files[str(path)] = digest(path)
        print('SOURCE_BN_ONLY', fold['target'], flush=True)
    freeze = {'at_local': datetime.now().isoformat(), 'count': 90, 'models': files,
              'main_target_scoring_not_started': not (OUTPUT/'target_access.json').exists()}
    assert freeze['main_target_scoring_not_started']
    (output/'source_freeze.json').write_text(json.dumps(freeze, indent=2)+'\n', encoding='utf-8')


def evaluate():
    p, old, stats, waves, folds = load(OUTPUT)
    frozen_models(OUTPUT)
    output = OUTPUT/'source_bn_diagnostic'
    config = read(output/'protocol.json')
    if config['source_file_sha256'] != digest(Path(__file__)) or (output/'results.json').exists():
        raise RuntimeError('Changed code or existing diagnostic result')
    freeze = read(output/'source_freeze.json')
    assert freeze['count'] == 90 and freeze['main_target_scoring_not_started']
    for path, expected in freeze['models'].items():
        assert digest(path) == expected
    access = {'at_local': datetime.now().isoformat(), 'source_freeze_at': freeze['at_local']}
    (output/'target_access.json').write_text(json.dumps(access, indent=2)+'\n', encoding='utf-8')
    assert datetime.fromisoformat(freeze['at_local']) < datetime.fromisoformat(access['at_local'])
    report = read(OUTPUT/'results.json')
    rows, errors, hashes = [], [], {}
    for fold in folds:
        _, _, target = fold_indices(stats['subjects'], stats['order'], fold)
        repetitions = []
        for seed in p['seeds']:
            c = torch.load(output/f's{fold["target"]:02d}_seed{seed}.pt', map_location='cpu', weights_only=True)
            model = EEGNetSmall(c['config'])
            model.load_state_dict(c['state_dict'])
            x = normalized_tensor(waves[target], np.array(c['source_mean']), np.array(c['source_scale']), 'cpu')
            logits = network_logits(model, x)
            save_prediction(output, fold['target'], NAME, seed, target, stats['labels'][target], logits,
                            logits.argmax(1), {**fold, 'seed': seed, 'primary_candidate': False, 'no_refit': True})
            path = output/'fold_predictions'/f's{fold["target"]:02d}_{NAME}_seed{seed}.npz'
            hashes[str(path)] = digest(path)
            with np.load(path, allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['scores'], logits)
                np.testing.assert_array_equal(saved['labels'], stats['labels'][target])
                ba, f1, matrix = integer_metrics(saved['labels'], saved['predictions'])
            repetitions.append({'seed': seed, 'ba': ba, 'macro_f1': f1, 'confusion': matrix})
        rows.append({'person': fold['target'], 'trials': len(target),
                     'ba': float(np.mean([r['ba'] for r in repetitions])),
                     'macro_f1': float(np.mean([r['macro_f1'] for r in repetitions])), 'per_seed': repetitions})
    values = np.array([r['ba'] for r in rows])
    base = np.array([r['ba'] for r in report['methods']['B0_ORIGINAL_EEGNET']['per_person']])
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 30, (10000,30))
    result = {'method': NAME, 'scope': 'Pre-score diagnostic control,not primary candidate,no target selection',
              'mean_person_ba': float(values.mean()), 'between_person_sd': float(values.std(ddof=1)),
              'mean_lowest8_ba': float(np.sort(values)[:8].mean()),
              'mean_person_macro_f1': float(np.mean([r['macro_f1'] for r in rows])),
              'person_95_ci': np.quantile(values[draws].mean(1), [.025,.975]).tolist(),
              'gain_vs_original': float((values-base).mean()),
              'paired_95_ci_descriptive_not_primary_gate': np.quantile((values-base)[draws].mean(1), [.025,.975]).tolist(),
              'per_person': rows, 'prediction_sha256': hashes,
              'scored_predictions': sum(r['trials'] for r in rows)*3, 'learned_weights_unchanged': True,
              'primary_gate_not_applied': True, 'confirmation_eeg_read': False, 'control_enabled': False}
    (output/'results.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: value for key,value in result.items() if key not in ('per_person','prediction_sha256')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare','evaluate'))
    args = parser.parse_args()
    {'prepare':prepare, 'evaluate':evaluate}[args.action]()

"""Verify source-only BN control changed no learned tensor; inspect variance."""
from pathlib import Path
import json

from mi_crossfield_stability import OUTPUT, HERE, read, digest, torch
import numpy as np


def main():
    output = OUTPUT/'source_bn_diagnostic'
    target = output/'buffer_audit.json'
    if target.exists():
        raise RuntimeError('Existing buffer audit preserved')
    protocol = read(OUTPUT/'protocol.json')
    freeze = read(output/'source_freeze.json')
    layers = ['block1.0.running_var', 'block1.2.running_var', 'block2.3.running_var']
    rows = []
    for path in sorted(output.glob('s*_seed*.pt')):
        original = HERE/protocol['original_run']/'network_checkpoints'/path.name
        assert digest(path) == freeze['models'][str(path)]
        a = torch.load(original, map_location='cpu', weights_only=True)['state_dict']
        b = torch.load(path, map_location='cpu', weights_only=True)['state_dict']
        for key in a:
            if not ('running_' in key or 'num_batches_tracked' in key):
                torch.testing.assert_close(a[key], b[key], rtol=0, atol=0)
        ratios = {}
        for key in layers:
            assert torch.isfinite(a[key]).all() and torch.isfinite(b[key]).all()
            assert (b[key] > 0).all()
            ratios[key] = float((a[key]/b[key]).median())
        rows.append({'model': path.name, 'learned_tensors_exact': True, 'layer_ratios': ratios})
    assert len(rows) == 90
    result = {'passed': True, 'models_checked': 90, 'all_learned_tensors_exact': True,
              'statistic': 'Per model median across channels via torch.median;then numpy median across90 models',
              'old_over_source_calibrated_variance_ratio_median':
                  {key: float(np.median([r['layer_ratios'][key] for r in rows])) for key in layers},
              'per_model': rows, 'source_model_freeze_sha256': digest(output/'source_freeze.json'),
              'script_sha256': digest(Path(__file__)), 'target_EEG_read': False,
              'interpretation': 'Measured source-statistics difference,not evidence of target accuracy or causal effect of Dropout alone'}
    target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key:value for key,value in result.items() if key != 'per_model'}, indent=2))


if __name__ == '__main__':
    main()

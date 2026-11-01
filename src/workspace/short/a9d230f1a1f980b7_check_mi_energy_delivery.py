"""Read-only post-score integrity and inline-display checks; no model fitting."""
from datetime import datetime
from pathlib import Path
import json
import math
import re

from audit_mi_person_transfer_counts import read, digest

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_energy_source_diagnostic_20261002'
CANVAS = Path('C:/Users/lenovo/.cursor/projects/ican_naoji/canvases/MI-energy-source.canvas.tsx')
FORMAL = Path('D:/ican/handoff/GuardianLoop_FROZEN_20261001.zip')


def close(shown, actual):
    assert math.isclose(shown, actual, rel_tol=0, abs_tol=1e-12), (shown, actual)


def main():
    destination = RUN / 'delivery_checks.json'
    if destination.exists():
        raise RuntimeError('Existing delivery evidence preserved')
    lock = read(RUN / 'lock.json')
    freeze = read(RUN / 'source_freeze.json')
    access = read(RUN / 'validation_access.json')
    features = read(RUN / 'feature_audit.json')
    results = read(RUN / 'results.json')
    verification = read(RUN / 'verification.json')
    audit = read(RUN / 'integer_count_audit.json')
    assert len(lock['source_sha256']) == 27 and len(lock['input_sha256']) == 11
    for source, expected in lock['source_sha256'].items():
        assert digest(Path(source)) == expected, source
        assert digest(RUN / 'code_snapshot' / Path(source).name) == expected
    assert len(list((RUN / 'code_snapshot').iterdir())) == 27
    for source, expected in lock['input_sha256'].items():
        assert digest(Path(source)) == expected, source
    assert freeze['new_fits'] == 60 and freeze['reused_models'] == 30
    assert freeze['total_states'] == 90
    for hashes, directory, count in (
        (freeze['files'], 'models', 180),
        (results['prediction_sha256'], 'validation_predictions', 90),
    ):
        assert len(hashes) == len(list((RUN / directory).iterdir())) == count
        for source, expected in hashes.items():
            assert digest(Path(source)) == expected, source
    assert lock['at_local'] < freeze['at_local'] < access['at_local']
    assert access['source_validation_only'] and not access['outer_target_scored']
    assert read(RUN / 'protocol.json') == read(HERE / 'mi_energy_protocol.json')
    assert digest(RUN / 'source_fold_manifest.json') == lock['source_fold_manifest_sha256']
    assert digest(RUN / 'features.npz') == features['features_sha256']
    assert features['normalized_byte_identical'] and features['all6080_scale_identity_probes']
    result_hash = digest(RUN / 'results.json')
    assert verification['passed'] and audit['passed']
    assert verification['results_sha256'] == audit['results_sha256'] == result_hash
    assert digest(RUN / 'solver_trace.json') == verification['solver_trace_sha256']
    assert read(RUN / 'solver_trace.json')['count'] == 90
    assert digest(FORMAL) == lock['formal_package_sha256']
    for field in ('outer_target_scored', 'board_accessed', 'arm_exported', 'control_enabled'):
        assert results[field] is False
    assert results['total_predictions'] == verification['predictions_recomputed'] == 54840
    assert verification['classes_exact']
    assert results['comparisons']['NORMALIZED_ENERGY_minus_NORMALIZED']['direction_gate'] is False

    canvas_source = CANVAS.read_text(encoding='utf-8')
    inline = re.search(r'const DATA = (\{[\s\S]*?\});\nconst percent', canvas_source)
    assert inline, 'Inline data required'
    data = json.loads(inline.group(1))
    assert data['result_sha'] == result_hash and data['tests'] == 130
    assert data['verification'] == verification
    assert data['completed'] == results['completed_at_local']
    for shown, actual in (('people', 'validation_people'), ('absent', 'absent_validation_people'),
                          ('trials', 'unique_validation_trials'),
                          ('flags', 'unique_validation_author_flags'),
                          ('predictions', 'total_predictions'),
                          ('appearances', 'person_appearances')):
        assert data[shown] == results[actual]
    assert [method['id'] for method in data['methods']] == ['NORMALIZED', 'NORMALIZED_ENERGY', 'ABSOLUTE']
    for method in data['methods']:
        actual = results['methods'][method['id']]
        for shown, metric in (('ba', 'mean_person_ba'), ('fit', 'descriptive_source_fit_mean_ba'),
                              ('f1', 'mean_person_f1'), ('weakest', 'mean_lowest7_ba')):
            close(method[shown], actual[metric])
        for shown, expected in zip(method['ci'], actual['descriptive_person95ci']):
            close(shown, expected)
        assert len(method['people']) == len(actual['per_person']) == 28
        for shown, person in zip(method['people'], actual['per_person']):
            assert shown['person'] == person['person']
            assert shown['appearances'] == len(person['appearances'])
            close(shown['ba'], person['ba'])
    assert len(data['comparisons']) == len(results['comparisons']) == 3
    for shown in data['comparisons']:
        actual = results['comparisons'][shown['id']]
        for shown_key, actual_key in (('primary', 'primary'), ('gate', 'direction_gate'),
                                      ('improved', 'people_improved'), ('declined', 'people_declined')):
            assert shown[shown_key] == actual[actual_key]
        close(shown['gain'], actual['mean_gain'])
        close(shown['weakest'], actual['lowest7_mean_difference'])
        for value, expected in zip(shown['ci'], actual['descriptive_paired_ci']):
            close(value, expected)
    assert re.findall(r"from ['\"]([^'\"]+)['\"]", canvas_source) == ['cursor/canvas']
    assert 'export default function' in canvas_source
    assert not any(token in canvas_source for token in ('fetch(', 'linear-gradient', 'radial-gradient', 'box-shadow'))
    assert all(token in canvas_source for token in ('源验证', '不是外层测试', '横轴', '纵轴', '来源：'))
    evidence = ('RESULTS.md', 'RUN_STATUS.md', 'lock.json', 'protocol.json', 'source_fold_manifest.json',
                'source_freeze.json', 'feature_audit.json', 'validation_access.json', 'verification.json',
                'integer_count_audit.json', 'solver_trace.json')
    checked = {
        'passed': True, 'results_sha256': result_hash, 'source_files_checked': 27,
        'source_snapshots_checked': 27, 'input_files_checked': 11, 'model_files_checked': 180,
        'prediction_files_checked': 90, 'scored_predictions': 54840,
        'locked_before_models_before_validation': True,
        'formal_package_unchanged': True, 'formal_package_sha256': digest(FORMAL),
        'outer_target_scored': False, 'canvas_methods_checked': 3, 'canvas_comparisons_checked': 3,
        'canvas_people_per_method_checked': 28, 'canvas_numeric_tolerance': 1e-12,
        'canvas_sha256': digest(CANVAS), 'canvas_host_open_status': 'queued',
        'canvas_build_status_sidecar_available': CANVAS.with_suffix('.status.json').exists(),
        'canvas_host_compilation_claimed': False,
        'evidence_sha256': {name: digest(RUN / name) for name in evidence},
        'route_sha256': digest(HERE / 'MI_CURRENT_ROUTE.md'),
        'script_sha256': digest(Path(__file__)), 'at_local': datetime.now().isoformat(),
    }
    destination.write_text(json.dumps(checked, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in checked.items() if key != 'evidence_sha256'}, ensure_ascii=False))


if __name__ == '__main__':
    main()

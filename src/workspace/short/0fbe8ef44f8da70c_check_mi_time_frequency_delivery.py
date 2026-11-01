"""Read-only checks of frozen results and inline display, then save provenance."""
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json
import math
import re

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_time_frequency_source_diagnostic_20261002'
CANVAS = Path('C:/Users/lenovo/.cursor/projects/ican_naoji/canvases/MI-time-frequency-source.canvas.tsx')
FORMAL = Path('D:/ican/handoff/GuardianLoop_FROZEN_20261001.zip')


def digest(path):
    hasher = sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def same_number(left, right):
    assert math.isclose(left, right, rel_tol=0, abs_tol=1e-12), (left, right)


def main():
    destination = RUN / 'delivery_checks.json'
    if destination.exists():
        raise RuntimeError('Existing delivery evidence preserved')
    lock = read(RUN / 'lock.json')
    freeze = read(RUN / 'source_freeze.json')
    access = read(RUN / 'validation_access.json')
    results = read(RUN / 'results.json')
    verification = read(RUN / 'verification.json')
    audit = read(RUN / 'integer_count_audit.json')
    protocol = read(RUN / 'protocol.json')
    assert len(lock['source_sha256']) == 21 and len(lock['input_sha256']) == 6
    for source, expected in lock['source_sha256'].items():
        assert digest(source) == expected, source
        assert digest(RUN / 'code_snapshot' / Path(source).name) == expected
    assert len(list((RUN / 'code_snapshot').iterdir())) == 21
    for source, expected in lock['input_sha256'].items():
        assert digest(source) == expected, source
    assert len(freeze['files']) == 240 and freeze['fitted_models'] == 120
    for source, expected in freeze['files'].items():
        assert digest(source) == expected, source
    assert len(list((RUN / 'models').iterdir())) == 240
    assert len(results['prediction_sha256']) == 120
    for source, expected in results['prediction_sha256'].items():
        assert digest(source) == expected, source
    assert len(list((RUN / 'validation_predictions').iterdir())) == 120
    assert lock['at_local'] < freeze['at_local'] < access['at_local']
    assert access['source_validation_only'] and not access['outer_target_scored']
    assert protocol == read(HERE / 'mi_time_frequency_protocol.json')
    assert digest(RUN / 'source_fold_manifest.json') == lock['source_fold_manifest_sha256']
    assert digest(RUN / 'features.npz') == read(RUN / 'feature_audit.json')['features_sha256']
    result_hash = digest(RUN / 'results.json')
    assert verification['passed'] and audit['passed']
    assert verification['results_sha256'] == audit['results_sha256'] == result_hash
    assert digest(RUN / 'solver_trace.json') == verification['solver_trace_sha256']
    assert read(RUN / 'solver_trace.json')['count'] == 120
    assert digest(FORMAL) == lock['formal_package_sha256']
    for field in ('outer_target_scored', 'board_accessed', 'arm_exported', 'control_enabled'):
        assert results[field] is False
    assert results['comparisons']['TIME2_FREQ2_minus_WHOLE']['direction_gate'] is False
    assert results['total_predictions'] == 73120 and results['unique_validation_trials'] == 5680

    canvas_source = CANVAS.read_text(encoding='utf-8')
    inline = re.search(r'const DATA = (\{[\s\S]*?\});\nconst percent', canvas_source)
    assert inline, 'Canvas must embed complete auditable data'
    data = json.loads(inline.group(1))
    assert data['results_sha'] == result_hash and data['tests'] == 105
    assert data['verification'] == verification
    assert data['validation_people'] == results['validation_people']
    assert data['absent'] == results['absent_validation_people']
    for shown, actual in (('appearances', 'person_appearances'), ('unique_trials', 'unique_validation_trials'),
                          ('flags', 'unique_validation_author_flags'), ('predictions', 'total_predictions')):
        assert data[shown] == results[actual]
    assert [method['id'] for method in data['methods']] == protocol['methods']
    for method in data['methods']:
        actual = results['methods'][method['id']]
        assert method['dimension'] == protocol['dimensions'][method['id']]
        for shown, metric in (('ba', 'mean_person_ba'), ('f1', 'mean_person_f1'),
                              ('sd', 'between_person_sd'), ('weakest7', 'mean_lowest7_ba')):
            same_number(method[shown], actual[metric])
        for shown, value in zip(method['ci'], actual['descriptive_person95ci']):
            same_number(shown, value)
        assert len(method['people']) == len(actual['per_person']) == 28
        for shown, person in zip(method['people'], actual['per_person']):
            assert shown['person'] == person['person']
            assert shown['appearances'] == len(person['appearances'])
            same_number(shown['ba'], person['ba'])
            same_number(shown['f1'], person['macro_f1'])
    assert len(data['comparisons']) == 5
    for shown in data['comparisons']:
        actual = results['comparisons'][shown['id']]
        assert shown['primary'] == actual['primary'] and shown['gate'] == actual['direction_gate']
        assert shown['improved'] == actual['people_improved'] and shown['declined'] == actual['people_declined']
        same_number(shown['gain'], actual['mean_gain'])
        same_number(shown['weakest7'], actual['lowest7_mean_difference'])
        for value, expected in zip(shown['ci'], actual['descriptive_paired_ci']):
            same_number(value, expected)
    assert re.findall(r"from ['\"]([^'\"]+)['\"]", canvas_source) == ['cursor/canvas']
    assert 'export default function' in canvas_source
    assert not any(token in canvas_source for token in ('fetch(', 'linear-gradient', 'radial-gradient', 'box-shadow'))
    assert '只有源验证成绩' in canvas_source and '不是独立最终确认' in canvas_source
    assert '横轴' in canvas_source and '纵轴' in canvas_source and '来源：' in canvas_source
    sidecar = CANVAS.with_suffix('.status.json')
    files = ['RESULTS.md', 'RUN_STATUS.md', 'lock.json', 'protocol.json', 'source_fold_manifest.json',
             'feature_audit.json', 'source_freeze.json', 'validation_access.json', 'verification.json',
             'integer_count_audit.json', 'solver_trace.json']
    checked = {
        'passed': True, 'results_sha256': result_hash, 'source_files_checked': 21,
        'source_snapshots_checked': 21, 'input_files_checked': 6, 'model_files_checked': 240,
        'prediction_files_checked': 120, 'scored_predictions': 73120,
        'locked_before_fitting_before_validation': True, 'formal_package_unchanged': True,
        'formal_package_sha256': digest(FORMAL), 'outer_target_scored': False,
        'canvas_methods_checked': 4, 'canvas_comparisons_checked': 5, 'canvas_people_per_method_checked': 28,
        'canvas_numeric_tolerance': 1e-12, 'canvas_sha256': digest(CANVAS),
        'canvas_host_open_status': 'queued', 'canvas_build_status_sidecar_available': sidecar.exists(),
        'canvas_host_compilation_claimed': False,
        'evidence_sha256': {str(RUN / name): digest(RUN / name) for name in files},
        'route_sha256': digest(HERE / 'MI_CURRENT_ROUTE.md'), 'script_sha256': digest(__file__),
        'at_local': datetime.now().isoformat(),
    }
    destination.write_text(json.dumps(checked, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in checked.items() if key != 'evidence_sha256'}, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Independent integer-only score audit; no fitting, torch, or original EEG."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RUN = HERE/'output/mi_crossfield_stability_20261001'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    if (RUN/'integer_count_audit.json').exists():
        raise RuntimeError('Existing audit preserved')
    p, lock, report = [read(RUN/name) for name in ('protocol.json', 'lock.json', 'results.json')]
    source_freeze = read(RUN/'source_training_complete.json')
    access = read(RUN/'target_access.json')
    assert datetime.fromisoformat(source_freeze['frozen_at_local']) < datetime.fromisoformat(access['at_local'])
    for path, expected in {**lock['source_sha256'], **lock['input_sha256'],
                           **source_freeze['artifact_sha256'], **report['prediction_sha256']}.items():
        assert sha(path) == expected, path
    old = HERE/p['original_run']
    with np.load(old/'statistics.npz', allow_pickle=False) as cache:
        subjects, labels, order = [cache[key] for key in ('subjects', 'labels', 'order')]
    assert len(labels) == 6080 and sorted(set(subjects)) == p['participants']
    folds = read(RUN/'fold_manifest.json')
    assert len(folds) == 30
    trial_manifest = read(RUN/'trial_manifest.json')
    unique = {(r['subject'], r['label'], r['class_trial_index_one_based']) for r in trial_manifest}
    assert len(unique) == len(trial_manifest) == 6080
    assert sum(r['voltage_bad'] or r['emg_bad'] for r in trial_manifest) == report['author_flagged_retained'] == 515
    assert sum((r['voltage_bad'] or r['emg_bad']) and r['original_order'] >= 60 for r in trial_manifest) == 379
    risk_spans = []
    for history_path in (RUN/'source_checkpoints').glob('*.json'):
        history = read(history_path)
        for epoch in history['history']:
            risks = np.array(epoch['source_ema_ce'])
            span = float((risks.max()-risks.min())/p['risk']['temperature'])
            risk_spans.append(span)
            assert span < 60., 'Numerical log floor would alter declared entropic budget'
    totals, metrics = {}, {}
    for method in p['methods']:
        per_person, seed_sd, f1s = [], [], []
        for fold in folds:
            target = fold['target']
            assert len(fold['fit_people']) == 26 and len(fold['validation_people']) == 3
            assert not set(fold['fit_people']) & set(fold['validation_people'])
            assert target not in fold['fit_people']+fold['validation_people']
            assert set(fold['fit_people']+fold['validation_people']+[target]) == set(p['participants'])
            indices = np.where((subjects == target) & (order >= 60))[0]
            row = next(r for r in report['methods'][method]['per_person'] if r['person'] == target)
            bas, fs = [], []
            for seed in p['seeds']:
                if method == 'B0_ORIGINAL_EEGNET':
                    path = old/'fold_predictions'/f's{target:02d}_C2_EEGNet_SMALL_seed{seed}.npz'
                else:
                    path = RUN/'fold_predictions'/f's{target:02d}_{method}_seed{seed}.npz'
                with np.load(path, allow_pickle=False) as data:
                    np.testing.assert_array_equal(data['indices'], indices)
                    np.testing.assert_array_equal(data['labels'], labels[indices])
                    np.testing.assert_array_equal(data['predictions'], data['scores'].argmax(1))
                    y, yhat = data['labels'], data['predictions']
                    assert set(y) == {0, 1} and set(yhat) <= {0, 1}
                    matrix = [[int(np.count_nonzero((y == i) & (yhat == j))) for j in (0, 1)] for i in (0, 1)]
                    ba = .5*(matrix[0][0]/sum(matrix[0])+matrix[1][1]/sum(matrix[1]))
                    f1 = .5*sum(2*matrix[i][i]/(sum(matrix[i])+sum(matrix[j][i] for j in (0, 1))) for i in (0, 1))
                    expected = next(r for r in row['per_seed'] if r['seed'] == seed)
                    assert matrix == expected['confusion']
                    np.testing.assert_allclose([ba, f1], [expected['ba'], expected['macro_f1']], rtol=0, atol=1e-14)
                    bas.append(ba)
                    fs.append(f1)
                    totals[method] = totals.get(method, 0)+len(y)
            per_person.append(np.mean(bas))
            seed_sd.append(np.std(bas, ddof=1))
            f1s.append(np.mean(fs))
            np.testing.assert_allclose([np.mean(bas), np.mean(fs), np.std(bas, ddof=1)],
                                       [row['ba'], row['macro_f1'], row['seed_sd']], rtol=0, atol=1e-14)
        metrics[method] = np.array(per_person)
        summary = report['methods'][method]
        np.testing.assert_allclose([np.mean(per_person), np.std(per_person, ddof=1), np.mean(np.sort(per_person)[:8]),
                                   np.mean(seed_sd), np.mean(f1s)],
                                  [summary['mean_person_ba'], summary['between_person_sd'], summary['mean_lowest8_ba'],
                                   summary['mean_seed_sd'], summary['mean_person_macro_f1']], rtol=0, atol=1e-14)
        assert np.count_nonzero(metrics[method] < .55) == summary['people_below_55']
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 30, (p['bootstrap']['draws'], 30))
    baseline = metrics[p['primary_reference']]
    passing = []
    for method, values in metrics.items():
        np.testing.assert_allclose(np.percentile(values[draws].mean(1), [2.5,97.5]),
                                   report['methods'][method]['person_bootstrap_95_ci'], rtol=0, atol=1e-14)
        if method == p['primary_reference']:
            continue
        delta = values-baseline
        interval = np.percentile(delta[draws].mean(1), [1.25,98.75])
        comparison = report['paired_vs_original_eegnet'][method]
        np.testing.assert_allclose(interval, comparison['adjusted_97_5_paired_ci'], rtol=0, atol=1e-14)
        np.testing.assert_allclose(delta, comparison['per_person_gain'], rtol=0, atol=1e-14)
        assert (np.count_nonzero(delta > 1e-12), np.count_nonzero(delta < -1e-12),
                np.count_nonzero(np.abs(delta) <= 1e-12)) == (comparison['people_improved'], comparison['people_declined'], comparison['people_tied'])
        low_gain = np.mean(np.sort(values)[:8])-np.mean(np.sort(baseline)[:8])
        sd_change = np.std(values, ddof=1)-np.std(baseline, ddof=1)
        gate = p['gate']
        accepted = (method in p['primary_candidates'] and np.mean(delta) >= gate['mean_ba_gain_min']
                    and interval[0] > gate['adjusted_paired_ci_lower_greater_than']
                    and low_gain >= gate['lowest8_mean_gain_min']
                    and sd_change <= gate['between_person_sd_increase_max'])
        assert bool(accepted) == comparison['stability_gate_passed']
        if accepted:
            passing.append(method)
    assert passing == report['passing']
    assert set(totals.values()) == {4280*3} and sum(totals.values()) == 64200
    diagnostic = RUN/'source_bn_diagnostic'
    diagnostic_report = read(diagnostic/'results.json')
    diagnostic_freeze = read(diagnostic/'source_freeze.json')
    diagnostic_protocol = read(diagnostic/'protocol.json')
    assert datetime.fromisoformat(diagnostic_protocol['declared_at_local']) < datetime.fromisoformat(access['at_local'])
    assert datetime.fromisoformat(diagnostic_freeze['at_local']) < datetime.fromisoformat(access['at_local'])
    assert diagnostic_protocol['source_file_sha256'] == sha(HERE/'mi_source_bn_diagnostic.py')
    for path, expected in {**diagnostic_freeze['models'], **diagnostic_report['prediction_sha256']}.items():
        assert sha(path) == expected
    diagnostic_rows = []
    for row in diagnostic_report['per_person']:
        bas, fs = [], []
        for seed_row in row['per_seed']:
            person, seed = row['person'], seed_row['seed']
            path = diagnostic/'fold_predictions'/f's{person:02d}_ORIGINAL_BN_ONLY_seed{seed}.npz'
            indices = np.where((subjects == person) & (order >= 60))[0]
            with np.load(path, allow_pickle=False) as data:
                np.testing.assert_array_equal(data['indices'], indices)
                np.testing.assert_array_equal(data['labels'], labels[indices])
                y, yhat = data['labels'], data['predictions']
                np.testing.assert_array_equal(yhat, data['scores'].argmax(1))
                matrix = [[int(np.count_nonzero((y == i) & (yhat == j))) for j in (0,1)] for i in (0,1)]
                ba = .5*(matrix[0][0]/sum(matrix[0])+matrix[1][1]/sum(matrix[1]))
                f1 = .5*sum(2*matrix[i][i]/(sum(matrix[i])+sum(matrix[j][i] for j in (0,1))) for i in (0,1))
                assert matrix == seed_row['confusion']
                np.testing.assert_allclose([ba,f1], [seed_row['ba'],seed_row['macro_f1']], rtol=0, atol=1e-14)
                bas.append(ba)
                fs.append(f1)
        np.testing.assert_allclose([np.mean(bas),np.mean(fs)], [row['ba'],row['macro_f1']], rtol=0, atol=1e-14)
        diagnostic_rows.append(np.mean(bas))
    values = np.array(diagnostic_rows)
    np.testing.assert_allclose([values.mean(), values.std(ddof=1), np.sort(values)[:8].mean()],
                              [diagnostic_report['mean_person_ba'],diagnostic_report['between_person_sd'],diagnostic_report['mean_lowest8_ba']], rtol=0, atol=1e-14)
    np.testing.assert_allclose(np.percentile((values-baseline)[draws].mean(1), [2.5,97.5]),
                              diagnostic_report['paired_95_ci_descriptive_not_primary_gate'], rtol=0, atol=1e-14)
    totals['ORIGINAL_BN_ONLY_DIAGNOSTIC'] = diagnostic_report['scored_predictions']
    assert totals['ORIGINAL_BN_ONLY_DIAGNOSTIC'] == 12840
    result = {'passed': True, 'integer_predictions_checked': sum(totals.values()), 'counts_by_method': totals,
              'participants_checked': p['participants'], 'author_flags_preserved': 515,
              'source_freeze_preceded_target_forward': True, 'paired_bootstrap_and_gate_recomputed': True,
              'max_risk_scaled_span': max(risk_spans), 'numerical_log_floor_inactive_on_all_real_epochs': True,
              'BN_diagnostic_locked_and_frozen_before_primary_target_access': True,
              'no_model_fitted': True, 'original_mat_read': False, 'confirmation_eeg_read': False,
              'results_sha256': sha(RUN/'results.json'), 'script_sha256': sha(Path(__file__)),
              'verified_at_local': datetime.now().isoformat()}
    (RUN/'integer_count_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

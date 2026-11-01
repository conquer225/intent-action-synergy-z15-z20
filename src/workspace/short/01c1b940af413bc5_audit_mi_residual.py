"""Independent NumPy count/split/bound audit: no Torch, fit or raw EEG forwards."""
from datetime import datetime
from pathlib import Path
import json
import numpy as np
from audit_mi_person_transfer_counts import read, digest, close

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_source_residual_20261002'
NEW = ('SOURCE_BOUNDED_RESIDUAL', 'SOURCE_FREE_RESIDUAL')


def counts(labels, predictions):
    matrix = [[int(sum((labels == i) & (predictions == j))) for j in (0, 1)] for i in (0, 1)]
    assert all(sum(row) > 0 for row in matrix)
    ba = sum(matrix[i][i] / sum(matrix[i]) for i in (0, 1)) / 2
    f1 = sum(2 * matrix[i][i] / (sum(matrix[i]) + sum(matrix[j][i] for j in (0, 1))) for i in (0, 1)) / 2
    return ba, f1, matrix


def main():
    target = RUN / 'integer_count_audit.json'
    if target.exists():
        raise RuntimeError('Existing audit preserved')
    p, result, cases, lock, freeze, access = [read(RUN / name) for name in
        ('protocol.json', 'results.json', 'case_manifest.json', 'lock.json', 'source_freeze.json', 'target_access.json')]
    assert len(cases) == 90 and freeze['selected_states'] == 180 and freeze['shared_ridge_solutions'] == 360
    assert not freeze['test_forwarded'] and not freeze['source_weights_changed']
    assert len(freeze['files']) == 360
    assert datetime.fromisoformat(lock['declared_at_local']) < datetime.fromisoformat(freeze['at_local']) < datetime.fromisoformat(access['at_local'])
    for path, expected in {**lock['source_sha256'], **lock['input_sha256'], **freeze['files']}.items():
        assert digest(Path(path)) == expected, path
    assert digest(RUN / 'case_manifest.json') == lock['case_manifest_sha256']
    prior = HERE / p['prior_run']
    assert cases == read(prior / 'case_manifest.json')
    original = HERE / read(prior / 'protocol.json')['original_run']
    manifest = read(original / 'trial_manifest.json')
    with np.load(original / 'statistics.npz', allow_pickle=False) as data:
        labels, people, order = [data[k] for k in ('labels', 'subjects', 'order')]
    assert len(labels) == len(manifest) == 6080 and sorted(set(people)) == p['participants']
    assert sum(r['voltage_bad'] or r['emg_bad'] for r in manifest) == 515
    for case in cases:
        own = people == case['person']
        for key, condition in (('personal_fit', own & (order < 80)), ('personal_validation', own & (order >= 80) & (order < 120)), ('test', own & (order >= 120))):
            np.testing.assert_array_equal(case[key], np.flatnonzero(condition))
        source = original / 'network_checkpoints' / f's{case["person"]:02d}_seed{case["seed"]}.pt'
        arrays = []
        for method in NEW:
            path = RUN / 'models' / f's{case["person"]:02d}_{method}_seed{case["seed"]}.npz'
            meta = read(path.with_suffix('.json'))
            assert meta['case'] == case and meta['method'] == method
            assert meta['all_source_tensors_unchanged'] and not meta['test_forwarded']
            assert meta['source_checkpoint_sha256'] == digest(source)
            np.testing.assert_array_equal(meta['fit_indices'], case['personal_fit'])
            np.testing.assert_array_equal(meta['validation_indices'], case['personal_validation'])
            history = meta['validation_candidates']
            configs = [(None, 0)] + [(i, strength) for strength in p['strengths_in_tie_preference_order'] for i in range(4)]
            assert len(history) == len(configs) == 13
            for row, (index, strength) in zip(history, configs):
                assert row['alpha_index'] == index and row['strength'] == strength
                assert row['alpha'] == (None if index is None else p['alphas_in_tie_preference_order'][index])
                matrix = np.array(row['confusion'])
                np.testing.assert_array_equal(matrix.sum(1), [20, 20])
                ba = np.diag(matrix).sum() / 40
                f1 = np.mean([2*matrix[i,i] / (matrix[i].sum()+matrix[:,i].sum()) for i in (0,1)])
                close([ba, f1], [row['validation_ba'], row['validation_f1']])
            best = int(np.argmax([r['validation_ba'] for r in history]))
            assert meta['selected_index'] == best and meta['selected'] == history[best]
            cap = p['bounded_probability_residual_cap'] if method == NEW[0] else None
            assert meta['cap'] == cap
            with np.load(path, allow_pickle=False) as state:
                np.testing.assert_array_equal(state['fit_indices'], case['personal_fit'])
                np.testing.assert_array_equal(state['validation_indices'], case['personal_validation'])
                assert state['coefficients'].shape == (4, 240) and state['intercepts'].shape == (4,)
                assert state['fit_features'].shape == (80, 240)
                assert state['fit_probability'].shape == (80,)
                for key in ('coefficients', 'intercepts', 'mean', 'scale', 'fit_probability'):
                    assert np.isfinite(state[key]).all()
                assert (state['scale'] > 0).all()
                assert int(state['selected_index']) == best
                assert int(state['alpha_index']) == (-1 if history[best]['alpha_index'] is None else history[best]['alpha_index'])
                assert float(state['strength']) == history[best]['strength'] and float(state['cap']) == (-1 if cap is None else cap)
                arrays.append({key: state[key].copy() for key in ('coefficients','intercepts','mean','scale','fit_features','fit_probability')})
        for key in arrays[0]:
            np.testing.assert_array_equal(arrays[0][key], arrays[1][key])
    draws = np.random.default_rng(p['bootstrap']['seed']).integers(0, 30, (p['bootstrap']['draws'], 30))
    summaries, total = {}, 0
    for method in p['methods']:
        values, f1s = [], []
        rows = result['methods'][method]['per_person']
        assert [r['person'] for r in rows] == p['participants']
        for row in rows:
            bas, fs = [], []
            for case in [c for c in cases if c['person'] == row['person']]:
                path = RUN / 'fold_predictions' / f's{case["person"]:02d}_{method}_seed{case["seed"]}.npz'
                assert digest(path) == result['prediction_sha256'][str(path)]
                with np.load(path, allow_pickle=False) as saved:
                    ids, y, pred, score = [saved[key] for key in ('indices','labels','predictions','scores')]
                    np.testing.assert_array_equal(ids, case['test'])
                    np.testing.assert_array_equal(y, labels[ids])
                    assert np.isfinite(score).all() and set(pred) <= {0,1}
                    expected_pred = score.argmax(1) if method == 'CROSS_ORIGINAL' else (score > (.5 if method in NEW else 0)).astype(int)
                    np.testing.assert_array_equal(pred, expected_pred)
                    if method not in NEW:
                        with np.load(prior / 'fold_predictions' / path.name, allow_pickle=False) as old:
                            for key in ('indices','labels','predictions','scores'):
                                np.testing.assert_array_equal(saved[key], old[key])
                    ba, f1, matrix = counts(y, pred)
                expected = next(r for r in row['per_seed'] if r['seed'] == case['seed'])
                assert matrix == expected['confusion']
                close([ba,f1], [expected['ba'],expected['macro_f1']])
                bas.append(ba); fs.append(f1); total += len(ids)
            assert row['trials'] == len(case['test'])
            close([np.mean(bas),np.mean(fs)], [row['ba'],row['macro_f1']])
            values.append(np.mean(bas)); f1s.append(np.mean(fs))
        values = np.array(values)
        expected = result['methods'][method]
        close([values.mean(),values.std(ddof=1),np.sort(values)[:8].mean(),np.mean(f1s)],
              [expected['mean_person_ba'],expected['between_person_sd'],expected['mean_lowest8_ba'],expected['mean_person_f1']])
        close(np.quantile(values[draws].mean(1), [.025,.975]), expected['person95ci'])
        summaries[method] = values
    pairs = [[p['primary_candidate'],p['primary_reference']]] + p['secondary_comparisons']
    for j, (candidate, reference) in enumerate(pairs):
        c = result['comparisons'][candidate+'_minus_'+reference]
        delta = summaries[candidate] - summaries[reference]
        ci = np.quantile(delta[draws].mean(1), [.025,.975])
        weak_delta = np.sort(summaries[candidate])[:8].mean()-np.sort(summaries[reference])[:8].mean()
        close(c['mean_gain'],delta.mean()); close(c['paired_ci'],ci); close(c['per_person_delta'],delta); close(c['lowest8_mean_difference'],weak_delta)
        assert c['primary'] == (j==0) and c['coverage'] == .95
        gate = bool(j==0 and delta.mean() >= p['development_gate']['gain_at_least'] and ci[0] > 0 and weak_delta >= -p['development_gate']['lowest8_mean_drop_at_most'])
        assert c['development_gate'] == gate
        assert c['people_improved'] == int(sum(delta>1e-12)) and c['people_declined'] == int(sum(delta< -1e-12))
    protected = 0
    for method in NEW:
        changed,rescued,harmed,fallbacks = 0,0,0,0
        configs = []
        for case in cases:
            name = f's{case["person"]:02d}_{method}_seed{case["seed"]}'
            meta = read(RUN / 'models' / (name+'.json'))
            configs.append({'person':case['person'],'seed':case['seed'],**meta['selected']})
            fallbacks += meta['selected']['strength'] == 0
            with np.load(RUN / 'fold_predictions' / (name+'.npz'), allow_pickle=False) as s, np.load(prior / 'fold_predictions' / f's{case["person"]:02d}_CROSS_ORIGINAL_seed{case["seed"]}.npz', allow_pickle=False) as b:
                # An independent stable sigmoid with clipped exponent reconstructs the old source probability.
                margin = b['scores'][:,1].astype(float)-b['scores'][:,0].astype(float)
                base = 1/(1+np.exp(np.clip(-margin,-700,700)))
                if method == NEW[0]:
                    cap = p['bounded_probability_residual_cap']*meta['selected']['strength']
                    assert np.max(np.abs(s['scores']-base)) <= cap+2e-5
                    safe = np.abs(base-.5) > cap+2e-5
                    np.testing.assert_array_equal(s['predictions'][safe],b['predictions'][safe])
                    protected += int(safe.sum())
                if meta['selected']['strength'] == 0:
                    np.testing.assert_array_equal(s['predictions'],b['predictions'])
                    np.testing.assert_allclose(s['scores'],base,rtol=2e-5,atol=2e-5)
                was,now = b['predictions']==b['labels'],s['predictions']==s['labels']
                changed += int(np.count_nonzero(b['predictions']!=s['predictions']))
                rescued += int(np.count_nonzero(~was & now)); harmed += int(np.count_nonzero(was & ~now))
        d = result['diagnostics'][method]
        assert [changed,rescued,harmed,fallbacks] == [d['changed_predictions'],d['rescued_predictions'],d['harmed_predictions'],d['identity_fallback_cases']]
        assert changed == rescued+harmed and d['denominator']==7440 and configs==d['selected_configs']
    unique = {i for c in cases for i in c['test']}
    assert len(unique)==result['scored_unique_trials']==2480
    assert result['scored_author_flags']==198==sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique)
    assert total==29760 and len(result['prediction_sha256'])==360
    audit = {'passed':True,'integer_predictions_checked':total,'selected_states_checked':180,'shared_fit_arrays_exact':True,
        'all_train_validation_test_indices_checked':True,'all_validation_ties_and_identity_selection_checked':True,
        'all_metrics_intervals_gate_and_change_counts_checked':True,'source_protected_predictions_checked':protected,
        'unique_trials':2480,'test_author_flags':198,'raw_mat_read':False,'board_accessed':False,
        'results_sha256':digest(RUN/'results.json'),'script_sha256':digest(Path(__file__)),'at_local':datetime.now().isoformat()}
    target.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(audit,indent=2))


if __name__=='__main__':
    main()

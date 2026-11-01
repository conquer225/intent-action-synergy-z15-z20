"""Independent counts/splits/selection/statistics; no Torch or model fitting."""
from datetime import datetime
from pathlib import Path
import json
import numpy as np
from audit_mi_person_transfer_counts import read, digest, close

HERE = Path(__file__).resolve().parent
RUN = HERE / 'output/mi_logcov_sourceonly_20261002'
NEW = ('LOGCOV_FULL_LR','LOGCOV_DIAG_LR')


def main():
    target = RUN/'integer_count_audit.json'
    if target.exists():
        raise RuntimeError('Completed audit preserved')
    p, result, folds, lock, freeze, access = [read(RUN/name) for name in
        ('protocol.json','results.json','fold_manifest.json','lock.json','source_freeze.json','target_access.json')]
    assert len(folds)==30 and freeze['selected_states']==60 and freeze['deterministic_fits']==240
    assert len(freeze['files'])==120 and not freeze['target_scored'] and not freeze['target_person_labels_used']
    assert datetime.fromisoformat(lock['declared_at_local']) < datetime.fromisoformat(freeze['at_local']) < datetime.fromisoformat(access['at_local'])
    assert access['this_marker_is_scoring_not_first_stateless_feature_access']
    for path, expected in {**lock['source_sha256'],**lock['input_sha256'],**freeze['files']}.items():
        assert digest(Path(path))==expected, path
    assert digest(RUN/'fold_manifest.json')==lock['fold_manifest_sha256']
    feature_audit = read(RUN/'feature_audit.json')
    assert feature_audit['stateless_per_trial'] and not feature_audit['labels_used'] and feature_audit['target_features_computed_before_fit']
    assert digest(RUN/'log_features.npy')==feature_audit['feature_sha256']
    original = HERE/p['original_run']; prior = HERE/p['prior_run']
    manifest = read(original/'trial_manifest.json')
    old_cases = read(prior/'case_manifest.json')
    full = np.load(RUN/'log_features.npy',allow_pickle=False)
    assert full.shape==(6080,36) and np.isfinite(full).all()
    with np.load(original/'statistics.npz',allow_pickle=False) as stats:
        labels, people, order = [stats[k] for k in ('labels','subjects','order')]
    assert len(labels)==len(manifest)==6080 and sorted(set(people))==p['participants']
    assert sum(r['voltage_bad'] or r['emg_bad'] for r in manifest)==515
    for fold in folds:
        old = [c for c in old_cases if c['person']==fold['person']]
        assert len(old)==3 and all(c['original_source_fold']==old[0]['original_source_fold'] for c in old)
        assert fold['fit_people']==old[0]['original_source_fold']['fit_people']
        assert fold['validation_people']==old[0]['original_source_fold']['validation_people']
        fit = np.flatnonzero(np.isin(people,fold['fit_people']))
        val = np.flatnonzero(np.isin(people,fold['validation_people']))
        test = np.flatnonzero((people==fold['person']) & (order>=120))
        np.testing.assert_array_equal(fold['fit_indices'],fit); np.testing.assert_array_equal(fold['validation_indices'],val)
        np.testing.assert_array_equal(fold['test'],test)
        assert len(fold['fit_people'])==26 and len(fold['validation_people'])==3
        assert not(set(fit)&set(val) or set(fit)&set(test) or set(val)&set(test))
        assert fold['person'] not in people[fit] and fold['person'] not in people[val]
        for method in NEW:
            path = RUN/'models'/f's{fold["person"]:02d}_{method}.npz'
            meta = read(path.with_suffix('.json'))
            assert meta['method']==method and meta['person']==fold['person'] and meta['deterministic']
            assert not meta['target_person_labels_used'] and not meta['test_scored']
            history = meta['validation_candidates']
            assert [r['C'] for r in history]==[.01,.1,1,10]
            for row in history:
                assert [r['person'] for r in row['per_person']]==fold['validation_people']
                ba=[]
                for person_row in row['per_person']:
                    matrix=np.array(person_row['confusion'])
                    expected_counts=np.bincount(labels[val][people[val]==person_row['person']],minlength=2)
                    np.testing.assert_array_equal(matrix.sum(1),expected_counts)
                    b=np.mean(np.diag(matrix)/matrix.sum(1))
                    f=np.mean(2*np.diag(matrix)/(matrix.sum(0)+matrix.sum(1)))
                    close([b,f],[person_row['ba'],person_row['macro_f1']]);ba.append(b)
                close(np.mean(ba),row['mean_person_ba'])
            selected=int(np.argmax([r['mean_person_ba'] for r in history]))
            assert selected==meta['selected_index'] and meta['selected']==history[selected]
            with np.load(path,allow_pickle=False) as state:
                columns=np.arange(36) if method==NEW[0] else np.array([0,8,15,21,26,30,33,35])
                np.testing.assert_array_equal(state['columns'],columns)
                np.testing.assert_array_equal(state['fit_indices'],fit);np.testing.assert_array_equal(state['validation_indices'],val)
                assert int(state['selected_index'])==selected and state['coefficients'].shape==(4,len(columns))
                assert state['intercepts'].shape==(4,) and (state['scale']>0).all()
                close(state['mean'],full[fit][:,columns].mean(0))
                scores=((full[val][:,columns]-state['mean'])/state['scale'])@state['coefficients'].T+state['intercepts']
                for i,row in enumerate(history):
                    pred=(scores[:,i]>0).astype(int)
                    for person_row in row['per_person']:
                        keep=people[val]==person_row['person'];y=labels[val][keep];pr=pred[keep]
                        matrix=[[int(sum((y==a)&(pr==b))) for b in (0,1)] for a in (0,1)]
                        assert matrix==person_row['confusion']
    draws=np.random.default_rng(p['bootstrap']['seed']).integers(0,30,(10000,30))
    arrays={};total=0;new_predictions=0
    for method in p['methods']:
        values,fs=[],[]; rows=result['methods'][method]['per_person']
        assert [r['person'] for r in rows]==p['participants']
        seeds=[0] if method in NEW else [42,43,44]
        assert result['methods'][method]['deterministic_new_model']==(method in NEW)
        for row,fold in zip(rows,folds):
            assert row['trials']==len(fold['test']) and [r['seed'] for r in row['per_seed']]==seeds
            bas,f1s=[],[]
            for seed in seeds:
                path=RUN/'fold_predictions'/f's{row["person"]:02d}_{method}_seed{seed}.npz'
                assert digest(path)==result['prediction_sha256'][str(path)]
                with np.load(path,allow_pickle=False) as saved:
                    ids,y,pred=saved['indices'],saved['labels'],saved['predictions']
                    np.testing.assert_array_equal(ids,fold['test']);np.testing.assert_array_equal(y,labels[ids])
                    computed=(saved['scores']>0).astype(int) if method in NEW else saved['scores'].argmax(1)
                    np.testing.assert_array_equal(pred,computed)
                    if method not in NEW:
                        with np.load(prior/'fold_predictions'/path.name,allow_pickle=False) as old:
                            for key in ('indices','labels','predictions','scores'):np.testing.assert_array_equal(saved[key],old[key])
                    matrix=np.array([[int(sum((y==a)&(pred==b))) for b in (0,1)] for a in (0,1)])
                    ba=np.mean(np.diag(matrix)/matrix.sum(1));f1=np.mean(2*np.diag(matrix)/(matrix.sum(0)+matrix.sum(1)))
                    expected=next(r for r in row['per_seed'] if r['seed']==seed)
                    assert matrix.tolist()==expected['confusion'];close([ba,f1],[expected['ba'],expected['macro_f1']])
                    bas.append(ba);f1s.append(f1);total+=len(ids)
                    if method in NEW:new_predictions+=len(ids)
            close([np.mean(bas),np.mean(f1s)],[row['ba'],row['macro_f1']])
            values.append(np.mean(bas));fs.append(np.mean(f1s))
        v=np.array(values);m=result['methods'][method];arrays[method]=v
        close([v.mean(),v.std(ddof=1),np.sort(v)[:8].mean(),np.mean(fs)],[m['mean_person_ba'],m['between_person_sd'],m['mean_lowest8_ba'],m['mean_person_f1']])
        close(np.quantile(v[draws].mean(1),[.025,.975]),m['person95ci'])
    for i,(candidate,reference) in enumerate([[p['primary_candidate'],p['primary_reference']]]+p['secondary_comparisons']):
        c=result['comparisons'][candidate+'_minus_'+reference]
        delta=arrays[candidate]-arrays[reference];ci=np.quantile(delta[draws].mean(1),[.025,.975])
        weak=np.sort(arrays[candidate])[:8].mean()-np.sort(arrays[reference])[:8].mean()
        close(c['mean_gain'],delta.mean());close(c['paired_ci'],ci);close(c['per_person_delta'],delta);close(c['lowest8_mean_difference'],weak)
        assert c['primary']==(i==0) and c['development_gate']==bool(i==0 and delta.mean()>=.02 and ci[0]>0 and weak>=-.01)
        assert c['people_improved']==int(sum(delta>1e-12)) and c['people_declined']==int(sum(delta< -1e-12))
    unique={i for fold in folds for i in fold['test']}
    assert total==result['total_predictions']==19840 and new_predictions==4960 and len(result['prediction_sha256'])==240
    assert len(unique)==result['scored_unique_trials']==2480
    assert sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique)==result['scored_author_flags']==198
    assert not result['personal_labels_used'] and not result['board_accessed'] and not result['control_enabled']
    audit={'passed':True,'integer_predictions_checked':total,'deterministic_new_predictions':new_predictions,
        'selected_states_checked':60,'all_source_fit_validation_target_indices_checked':True,
        'all240_validation_confusions_and60_choices_checked':True,'unchanged_reference_arrays_exact':True,
        'all_metrics_intervals_gate_recomputed':True,'unique_trials':2480,'author_flags_retained':198,
        'model_fitted':False,'raw_mat_read':False,'board_accessed':False,
        'results_sha256':digest(RUN/'results.json'),'script_sha256':digest(Path(__file__)),'at_local':datetime.now().isoformat()}
    target.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8');print(json.dumps(audit,indent=2))


if __name__=='__main__':main()

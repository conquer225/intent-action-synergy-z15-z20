"""Independent source-validation counts, frozen inputs and person weighting."""
from datetime import datetime
from pathlib import Path
import json
import numpy as np
from audit_mi_person_transfer_counts import read,digest,close

HERE=Path(__file__).resolve().parent
RUN=HERE/'output/mi_time_frequency_source_diagnostic_20261002'


def main():
    target=RUN/'integer_count_audit.json'
    if target.exists():raise RuntimeError('Completed audit preserved')
    p,r,lock,freeze,access=[read(RUN/name) for name in
        ('protocol.json','results.json','lock.json','source_freeze.json','validation_access.json')]
    assert freeze['fitted_models']==120 and len(freeze['files'])==240
    assert not freeze['source_validation_scored'] and not freeze['outer_target_scored']
    assert datetime.fromisoformat(lock['at_local'])<datetime.fromisoformat(freeze['at_local'])<datetime.fromisoformat(access['at_local'])
    assert access['source_validation_only'] and not access['outer_target_scored']
    for path,expected in {**lock['source_sha256'],**lock['input_sha256'],**freeze['files'],**r['prediction_sha256']}.items():
        assert digest(Path(path))==expected,path
    feature_audit=read(RUN/'feature_audit.json')
    assert feature_audit['stateless_label_free'] and feature_audit['all6080_identity_probes_checked']
    assert not feature_audit['outer_target_scored'] and feature_audit['whole_matches_previous_features']
    assert digest(RUN/'features.npz')==feature_audit['features_sha256']
    assert digest(RUN/'source_fold_manifest.json')==lock['source_fold_manifest_sha256']
    original=HERE/p['original_run'];manifest=read(original/'trial_manifest.json')
    original_folds=read(original/'fold_manifest.json');folds=read(RUN/'source_fold_manifest.json')
    with np.load(original/'statistics.npz',allow_pickle=False) as saved:
        people,labels=saved['subjects'].copy(),saved['labels'].copy()
    assert len(manifest)==len(labels)==6080
    np.testing.assert_array_equal(labels,[a['label'] for a in manifest])
    np.testing.assert_array_equal(people,[a['subject'] for a in manifest])
    assert sum(a['voltage_bad'] or a['emg_bad'] for a in manifest)==515
    with np.load(RUN/'features.npz',allow_pickle=False) as cache:
        features={m:cache[m].copy() for m in p['methods']}
    validation_people=sorted({person for f in folds for person in f['validation_people']})
    assert len(validation_people)==28 and validation_people==r['validation_people']
    assert set(p['participants'])-set(validation_people)=={14,28}
    appearances={person:sum(person in f['validation_people'] for f in folds) for person in validation_people}
    assert min(appearances.values())==1 and max(appearances.values())==7 and sum(appearances.values())==90
    total=0;unique=set();values={}
    draws=np.random.default_rng(p['bootstrap']['seed']).integers(0,28,(10000,28))
    for method in p['methods']:
        per_person={person:[] for person in validation_people}
        for fold,old in zip(folds,original_folds):
            assert all(fold[k]==old[k] for k in old)
            fit=np.flatnonzero(np.isin(people,fold['fit_people']));val=np.flatnonzero(np.isin(people,fold['validation_people']))
            np.testing.assert_array_equal(fit,fold['fit_indices']);np.testing.assert_array_equal(val,fold['validation_indices'])
            assert len(set(people[fit]))==26 and len(set(people[val]))==3 and not(set(fit)&set(val))
            assert fold['target'] not in people[fit] and fold['target'] not in people[val]
            unique.update(val.tolist())
            model=RUN/'models'/f'outer{fold["target"]:02d}_{method}.npz'
            meta=read(model.with_suffix('.json'))
            assert meta['C']==.1 and not meta['source_validation_used_for_selection'] and not meta['outer_target_scored']
            assert meta['dimensions']==p['dimensions'][method]
            with np.load(model,allow_pickle=False) as state:
                np.testing.assert_array_equal(state['fit_indices'],fit)
                assert len(state['coef'])==p['dimensions'][method]
                np.testing.assert_allclose(state['mean'],features[method][fit].mean(0),rtol=1e-10,atol=1e-10)
                expected_scale=features[method][fit].std(0)
                expected_scale[expected_scale==0]=1
                np.testing.assert_allclose(state['scale'],expected_scale,rtol=1e-10,atol=1e-10)
                close(state['factor'],np.sqrt(36/p['dimensions'][method]))
                expected=((features[method][val]-state['mean'])/state['scale']*state['factor'])@state['coef']+state['intercept']
            predpath=RUN/'validation_predictions'/f'outer{fold["target"]:02d}_{method}.npz'
            with np.load(predpath,allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved['indices'],val);np.testing.assert_array_equal(saved['people'],people[val])
                np.testing.assert_array_equal(saved['labels'],labels[val]);np.testing.assert_array_equal(saved['predictions'],(expected>0).astype(int))
                np.testing.assert_allclose(saved['scores'],expected,rtol=1e-12,atol=1e-12)
                for person in fold['validation_people']:
                    keep=people[val]==person;y=labels[val][keep];pr=saved['predictions'][keep]
                    cm=np.array([[int(np.sum((y==a)&(pr==b))) for b in (0,1)] for a in (0,1)])
                    ba=float(np.mean(np.diag(cm)/cm.sum(1)));f1=float(np.mean(2*np.diag(cm)/(cm.sum(0)+cm.sum(1))))
                    per_person[person].append({'outer_fold':fold['target'],'trials':len(y),'ba':ba,'macro_f1':f1,'confusion':cm.tolist()})
                total+=len(val)
        rows=r['methods'][method]['per_person'];assert [a['person'] for a in rows]==validation_people
        for row in rows:
            expected=per_person[row['person']]
            assert row['appearances']==expected and len(expected)==appearances[row['person']]
            close(row['ba'],np.mean([a['ba'] for a in expected]));close(row['macro_f1'],np.mean([a['macro_f1'] for a in expected]))
        v=np.array([a['ba'] for a in rows]);m=r['methods'][method];values[method]=v
        close([v.mean(),v.std(ddof=1),np.sort(v)[:7].mean(),np.mean([a['macro_f1'] for a in rows])],
            [m['mean_person_ba'],m['between_person_sd'],m['mean_lowest7_ba'],m['mean_person_f1']])
        close(np.quantile(v[draws].mean(1),[.025,.975]),m['descriptive_person95ci'])
    for i,(candidate,reference) in enumerate([[p['primary_candidate'],p['primary_reference']]]+p['secondary_comparisons']):
        c=r['comparisons'][candidate+'_minus_'+reference];delta=values[candidate]-values[reference]
        ci=np.quantile(delta[draws].mean(1),[.025,.975]);weak=np.sort(values[candidate])[:7].mean()-np.sort(values[reference])[:7].mean()
        close(c['mean_gain'],delta.mean());close(c['descriptive_paired_ci'],ci);close(c['per_person_delta'],delta);close(c['lowest7_mean_difference'],weak)
        assert c['primary']==(i==0) and c['direction_gate']==bool(i==0 and delta.mean()>=.02 and ci[0]>0 and weak>=-.01)
        assert c['people_improved']==int(sum(delta>1e-12)) and c['people_declined']==int(sum(delta< -1e-12))
    assert len(r['prediction_sha256'])==120 and total==r['total_predictions']==r['predictions_per_method']*4
    assert len(unique)==r['unique_validation_trials'] and r['person_appearances']==90
    assert sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique)==r['unique_validation_author_flags']
    assert not r['outer_target_scored'] and not r['board_accessed'] and not r['arm_exported'] and not r['control_enabled']
    audit={'passed':True,'integer_predictions_checked':total,'models_checked':120,'folds_checked':30,
        'unique_validation_people':28,'appearances_checked':90,'unique_validation_trials':len(unique),
        'validation_author_flags_retained':r['unique_validation_author_flags'],
        'all_source_indices_outer_exclusions_checked':True,'person_weighting_checked':True,
        'all_metrics_descriptive_intervals_gate_checked':True,'outer_target_scored':False,
        'results_sha256':digest(RUN/'results.json'),'script_sha256':digest(Path(__file__)),'at_local':datetime.now().isoformat()}
    target.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8');print(json.dumps(audit,indent=2))


if __name__=='__main__':main()

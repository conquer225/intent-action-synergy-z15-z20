"""Independent NumPy count/split/bootstrap audit. No Torch, model fit or raw MAT."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
RUN = HERE/'output/mi_person_transfer_diagnostic_20261002'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def close(actual,expected):
    np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-14)


def main():
    target=RUN/'integer_count_audit.json'
    if target.exists():
        raise RuntimeError('Existing audit preserved')
    p=read(RUN/'protocol.json')
    result=read(RUN/'results.json')
    cases=read(RUN/'case_manifest.json')
    lock=read(RUN/'lock.json')
    freeze=read(RUN/'source_freeze.json')
    access=read(RUN/'target_access.json')
    assert len(cases)==90 and freeze['fitted_models']==270
    assert datetime.fromisoformat(lock['declared_at_local']) < datetime.fromisoformat(freeze['at_local']) < datetime.fromisoformat(access['at_local'])
    for path,expected in {**lock['source_sha256'],**lock['input_sha256'],**freeze['files']}.items():
        assert digest(Path(path))==expected
    assert digest(RUN/'case_manifest.json')==lock['case_manifest_sha256']
    original=HERE/p['original_run']
    manifest=read(original/'trial_manifest.json')
    with np.load(original/'statistics.npz',allow_pickle=False) as data:
        labels,people,order=[data[k] for k in ('labels','subjects','order')]
    assert len(labels)==6080 and sorted(set(people))==p['participants']
    assert sum(r['voltage_bad'] or r['emg_bad'] for r in manifest)==515
    for case in cases:
        person=case['person']
        fit,val,test=[np.array(case[k]) for k in ('personal_fit','personal_validation','test')]
        for indices,condition in ((fit,(people==person)&(order<80)),(val,(people==person)&(order>=80)&(order<120)),(test,(people==person)&(order>=120))):
            np.testing.assert_array_equal(indices,np.flatnonzero(condition))
        assert len(fit)==80 and len(val)==40 and len(test) in (80,120)
        assert not(set(fit)&set(test) or set(val)&set(test) or set(fit)&set(val))
        for key,count,perclass,allowed in (('matched_fit',80,40,case['original_source_fold']['fit_people']),('matched_validation',40,20,case['original_source_fold']['validation_people'])):
            ids=np.array(case[key])
            assert len(ids)==len(set(ids))==count and sorted(set(people[ids]))==allowed and person not in people[ids]
            np.testing.assert_array_equal(np.bincount(labels[ids]),[perclass,perclass])
            quota,remainder=divmod(perclass,len(allowed))
            for cls in (0,1):
                counts=np.array([sum((people[ids]==g)&(labels[ids]==cls)) for g in allowed])
                assert set(counts).issubset({quota,quota+1}) and sum(counts==quota+1)==remainder
        assert not(set(case['matched_fit'])&set(case['matched_validation']))
    draws=np.random.default_rng(p['bootstrap']['seed']).integers(0,30,(10000,30))
    arrays={}
    total=0
    for method in p['methods']:
        values,fs=[] ,[]
        rows=result['methods'][method]['per_person']
        assert [r['person'] for r in rows]==p['participants']
        for row in rows:
            bas,f1s=[],[]
            for case in [c for c in cases if c['person']==row['person']]:
                path=RUN/'fold_predictions'/f's{case["person"]:02d}_{method}_seed{case["seed"]}.npz'
                assert digest(path)==result['prediction_sha256'][str(path)]
                with np.load(path,allow_pickle=False) as saved:
                    ids,y,pred=saved['indices'],saved['labels'],saved['predictions']
                    np.testing.assert_array_equal(ids,case['test'])
                    np.testing.assert_array_equal(y,labels[ids])
                    computed=(saved['scores']>0).astype(int) if method=='SOURCE_PERSON_HEAD' else saved['scores'].argmax(1)
                    np.testing.assert_array_equal(pred,computed)
                    matrix=[[int(sum((y==i)&(pred==j))) for j in (0,1)] for i in (0,1)]
                    ba=(matrix[0][0]/sum(matrix[0])+matrix[1][1]/sum(matrix[1]))/2
                    f1=sum(2*matrix[i][i]/(sum(matrix[i])+sum(matrix[j][i] for j in (0,1))) for i in (0,1))/2
                    expected=next(r for r in row['per_seed'] if r['seed']==case['seed'])
                    assert matrix==expected['confusion']
                    close([ba,f1],[expected['ba'],expected['macro_f1']])
                    bas.append(ba); f1s.append(f1); total+=len(ids)
            close([np.mean(bas),np.mean(f1s)],[row['ba'],row['macro_f1']])
            values.append(np.mean(bas)); fs.append(np.mean(f1s))
        values=np.array(values)
        summary=result['methods'][method]
        close([values.mean(),values.std(ddof=1),np.sort(values)[:8].mean(),np.mean(fs)],
              [summary['mean_person_ba'],summary['between_person_sd'],summary['mean_lowest8_ba'],summary['mean_person_f1']])
        close(np.quantile(values[draws].mean(1),[.025,.975]),summary['person95ci'])
        arrays[method]=values
    for name,comparison in result['comparisons'].items():
        candidate,reference=name.split('_minus_')
        delta=arrays[candidate]-arrays[reference]
        tail=(1-comparison['coverage'])/2
        ci=np.quantile(delta[draws].mean(1),[tail,1-tail])
        close(delta.mean(),comparison['mean_gain']); close(ci,comparison['paired_ci'])
        close(delta,comparison['per_person_delta'])
        expected_gate=bool(comparison['primary'] and delta.mean()>=.05 and ci[0]>0)
        assert comparison['diagnostic_headroom_gate']==expected_gate
    assert total==29760 and len(result['prediction_sha256'])==360
    unique_test={i for c in cases for i in c['test']}
    assert len(unique_test)==result['scored_unique_trials']==2480
    assert sum(manifest[i]['voltage_bad'] or manifest[i]['emg_bad'] for i in unique_test)==result['scored_author_flags']
    audit={'passed':True,'integer_predictions_checked':total,'predictions_per_condition':7440,
           'unique_common_test_trials':2480,'test_author_flags':result['scored_author_flags'],
           'source_freeze_before_late_test':True,'all_splits_and_budget_quotas_checked':True,
           'all_confusion_BA_F1_and_bootstrap_recomputed':True,'no_model_fitted':True,
           'raw_mat_read':False,'confirmation_eeg_read':False,'results_sha256':digest(RUN/'results.json'),
           'script_sha256':digest(Path(__file__)),'at_local':datetime.now().isoformat()}
    target.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(audit,indent=2))


if __name__=='__main__':
    main()

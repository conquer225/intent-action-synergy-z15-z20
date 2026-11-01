"""PC numerical references and coverage gate for captured installed-release calls."""
from collections import Counter
import argparse
import json
from pathlib import Path
import sys

import numpy as np

from accept_frozen_release import OUT, save


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT)
    parser.add_argument('--case',choices=('full_load','pause_then_reader_fault'))
    args=parser.parse_args()
    OUT=args.output.resolve()
    snapshot=OUT/'installed_runtime'
    sys.path.insert(0,str(snapshot))
    from cyton_covariance import CovarianceSVM, log_covariance
    from cyton_sqi import CausalEEGFilter
    from cyton_fatigue import FourChannelFatigue
    from ssvep_core import canonical_correlation
    emotion=CovarianceSVM(snapshot/'gameemo_covariance_svm.npz')
    fatigue=FourChannelFatigue(snapshot/'cyton_fatigue_overlap4.json')
    weights=dict(np.load(snapshot/'seed_shadow_weights.npz',allow_pickle=False))
    mi = None
    if (snapshot/'experimental_eegnet.npz').is_file():
        from mi_eegnet_portable import OfflineEEGNet
        mi = OfflineEEGNet(snapshot/'experimental_eegnet.npz',allow_experimental=True)
    plan=json.loads((OUT/'PLAN.json').read_text())
    results={}
    for case in ([args.case] if args.case else plan['cases']):
        folder=OUT/case
        report=json.loads((folder/'report.json').read_text())
        publications=json.loads((folder/'publications.json').read_text())
        calls=json.loads((folder/'numerical_calls.json').read_text())
        filters={}
        errors=Counter(); counts=Counter()
        with np.load(folder/'numerical_calls.npz',allow_pickle=False) as arrays:
            for call in calls:
                task=call['task']; counts[task]+=1
                a={k:arrays[v] for k,v in call.items() if k!='task'}
                if task=='filter':
                    instance=int(a['instance'])
                    filters.setdefault(instance,CausalEEGFilter())
                    predicted=filters[instance].process(a['input']); expected=a['output']
                elif task=='covariance':
                    predicted=np.concatenate([log_covariance(b) for b in a['bands']]); expected=a['output']
                elif task=='emotion':
                    label,votes,predicted=emotion.predict_feature(a['input'])
                    assert label==int(a['label']) and np.array_equal(votes,a['votes'])
                    expected=a['scores']
                elif task=='de':
                    predicted=(.5*np.log(2*np.pi*np.e*np.maximum(np.var(a['ring'],axis=0),1e-12))).reshape(-1)
                    expected=a['output']
                elif task=='fatigue':
                    predicted=fatigue._predict(a['input']); expected=a['output']
                elif task=='seed':
                    predicted=weights['weight']@(a['input']-a['mean'])+weights['bias']; expected=a['scores']
                    assert int(weights['classes'][np.argmax(predicted)])==int(a['label'])
                elif task=='ssvep':
                    predicted=np.array([canonical_correlation(a['input'],r,regularization=float(a['regularization']))
                                        for r in a['references']]); expected=a['output']
                    assert np.argmax(predicted)==np.argmax(expected)
                elif task=='mi' and mi is not None:
                    predicted=mi.logits(a['input']); expected=a['output']
                    np.testing.assert_array_equal(np.argmax(predicted,axis=1),np.argmax(expected,axis=1))
                else:
                    raise ValueError(task)
                error=float(np.max(np.abs(np.asarray(predicted)-expected)))
                errors[task]=max(errors[task],error)
                np.testing.assert_allclose(predicted,expected,
                    atol=1e-4 if task=='mi' else plan['numerical_atol'],
                    rtol=0 if task=='mi' else plan['numerical_rtol'])
        tasks={task:[r for r in publications if r['task']==task] for task in ('primary','seed','ssvep')}
        coverage={
            'emotion_prediction_publications':sum(bool(r['value'].get('emotion',{}).get('valid')) for r in tasks['primary']),
            'fatigue_prediction_publications':sum(r['value'].get('state')=='prediction' and r['value'].get('valid') for r in tasks['primary']),
            'seed_prediction_publications':sum(r['value'].get('state')=='prediction' and r['value'].get('valid') for r in tasks['seed']),
            'ssvep_candidate_publications':sum(r['value'].get('state')=='candidate_only' and r['value'].get('valid') for r in tasks['ssvep'])}
        prediction_ages=[r['value']['input_age_at_prediction_seconds']*1000
                         for r in tasks['primary'] if r['value'].get('valid')
                         and r['value'].get('state')=='prediction']
        assert prediction_ages and max(prediction_ages)<3000
        finals={task:rows[-1]['value'] for task,rows in tasks.items()}
        cleared=all(not value.get('valid') for value in finals.values())
        cleared &= not finals['primary'].get('emotion',{}).get('valid',False)
        cleared &= finals['ssvep'].get('scores') is None and finals['ssvep'].get('frequency_hz') is None
        cleared &= 'class_id' not in finals['seed'] and 'scores' not in finals['seed']
        assert cleared,finals
        assert not report['monitor_errors'] and not report['remaining_children']
        assert report['packet_input_age_p95_ms']<plan['p95_input_age_ms_limit']
        assert report['packet_input_age_max_ms']<plan['max_input_age_ms_limit']
        assert report['filter_backend']=='arm'
        recovery=None
        if case=='full_load':
            assert report['packets_consumed']==report['packets_expected']==39000
            assert report['error'] is None
            assert all(coverage.values()),coverage
            assert all(counts[task]>0 for task in ('emotion','fatigue','seed','ssvep')),counts
        else:
            assert report['packets_consumed']==37000
            assert 'CytonReaderError' in report['error']
            assert finals['primary']['reason']=='READER_SERIAL_IO_ERROR'
            idle=next(r for r in tasks['primary'] if r['value'].get('reason')=='STREAM_IDLE')
            before=[r for r in tasks['primary'] if r['elapsed_seconds']<idle['elapsed_seconds']]
            assert any(r['value'].get('state')=='prediction' and r['value'].get('valid') for r in before)
            assert not idle['value']['valid'] and not idle['value']['emotion']['valid']
            resumed=[r for r in tasks['ssvep'] if r['elapsed_seconds']>idle['elapsed_seconds']
                     and r['value']['state']=='candidate_only']
            assert resumed,'SSVEP did not recover after the short interruption'
            withdrawals={}
            for task in ('seed','ssvep'):
                withdrawn=[r for r in tasks[task] if not r['value']['valid']
                           and r['value']['state']=='no_data'
                           and abs(r['elapsed_seconds']-idle['elapsed_seconds'])<1]
                assert withdrawn,(task,'No idle withdrawal near the primary idle event')
                withdrawals[task]=withdrawn[0]['elapsed_seconds']
            recovery={'primary_idle_elapsed_s':idle['elapsed_seconds'],
                      'shadow_idle_elapsed_s':withdrawals,
                      'ssvep_candidate_resumed_elapsed_s':resumed[0]['elapsed_seconds'],
                      'primary_does_not_reuse_pre_gap_prediction':True,
                      'fatigue_recalibration_completion_in_this_fault_run':False}
        results[case]={'passed':True,'coverage':coverage,'numerical_call_counts':dict(counts),
                       'numerical_max_abs_error':dict(errors),'endpoints_cleared':bool(cleared),
                       'final_states':{task:value['state'] for task,value in finals.items()},
                       'input_age_p95_ms':report['packet_input_age_p95_ms'],
                       'input_age_max_ms':report['packet_input_age_max_ms'],
                       'fatigue_prediction_input_age_p95_ms':float(np.quantile(prediction_ages,.95)),
                       'fatigue_prediction_input_age_max_ms':float(max(prediction_ages)),
                       'cpu_seconds':report['parent_cpu_seconds']+report['children_cpu_seconds'],
                       'peak_rss_kib_with_audit_buffers':report['parent_peak_rss_kib'],
                       'packets_consumed':report['packets_consumed']}
        if recovery is not None:
            results[case]['recovery']=recovery
    if args.case:
        save(OUT/args.case/'REFERENCE.json',results[args.case])
        print(json.dumps(results,indent=2))
        return
    before=json.loads((OUT/'before.json').read_text());after=json.loads((OUT/'after.json').read_text())
    assert before['boot_id']==after['boot_id']
    assert before['installed_hashes']==after['installed_hashes']
    assert before['boot_hashes']==after['boot_hashes']
    audit={'passed':True,'release_id':plan['release_id'],'cases':results,
           'runtime_and_boot_files_unchanged':True,'live_service_restored':True,
           'real_cyton_stream_validated':False,'recognition_accuracy_validated':False,
           'scope':'Full installed ARM main loop, packet reader, four tasks, quality gates and publications. '
                   'PC references recompute captured actual filter/feature/model calls; CCA uses uncached reference. '
                   'Timing/RSS include replay-only numerical audit; browser rendering, radio, actuators excluded.'}
    save(OUT/'ACCEPTANCE.json',audit)
    print(json.dumps(audit,indent=2))


if __name__=='__main__':
    main()

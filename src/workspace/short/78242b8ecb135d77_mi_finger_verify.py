"""Recompute every frozen fold metric from predictions and audit metadata disagreements."""
import torch  # Load Windows torch before scipy/sklearn dependencies.
import json
import numpy as np
from mi_finger_baseline import metrics, split_people
from mi_finger_data import RUN, write_json, sha256_file


def main():
    protocol=json.loads((RUN/'protocol.json').read_text(encoding='utf-8'))
    audit=json.loads((RUN/'data_audit.json').read_text(encoding='utf-8'))
    results=json.loads((RUN/'results.json').read_text(encoding='utf-8'))
    counter=json.loads(audit['metadata']['sourcedata/counterbalancing_log.json']['text'])['ParticipantBlockAssignment']
    contradictions=[]
    for name,metadata in audit['metadata'].items():
        if not name.endswith('_eeg.json'): continue
        data=json.loads(metadata['text']); person=name.split('/')[0]
        reported=data['BlockAssignment']['original_first_condition']
        logged=counter[person]['block1_condition']
        if reported!=logged:
            contradictions.append(dict(path=name,metadata_first_condition=reported,log_first_condition=logged))
    native_samples=sum(int(round(r['seconds']*r['fs'])) for r in audit['records'])
    event_rows=sum(r['events']['rows'] for r in audit['records'])
    marker_counts={task:sum(sum(r['cue_counts'].values()) for r in audit['records'] if r['task']==task)
                   for task in ('random','sequential')}
    recomputed={}; prediction_count=0
    for fold in results['folds']:
        fit,val=split_people(protocol,fold['target'])
        assert fit==fold['fit_people'] and val==fold['validation_people']
        assert not(set(fit)&set(val)) and fold['target'] not in fit+val
        assert not(set(fit+val+[fold['target']]) & set(protocol['confirmation_people']))
        pred=np.load(RUN/'folds'/f'{fold["target"]}_predictions.npz')
        if len(set(pred['trial_id']))!=len(pred['labels']): raise ValueError('Duplicate trial IDs')
        names=['bandpower_ERD_LDA','motor4_LDA','occipital2_LDA','precue8_LDA','time_only_lookup']
        for name in names:
            actual=metrics(pred['labels'],pred[name]); expected=fold['methods'][name]
            for key in ('balanced_accuracy','macro_f1'):
                np.testing.assert_allclose(actual[key],expected[key],atol=1e-12,rtol=0)
            assert actual['confusion_matrix']==expected['confusion_matrix']
            recomputed.setdefault(name,[]).append(actual['balanced_accuracy'])
            prediction_count+=len(pred['labels'])
        scores=[]
        for seed,expected in zip(protocol['eegnet']['seeds'],fold['methods']['EEGNet5']['seeds']):
            actual=metrics(pred['labels'],pred[f'EEGNet5_seed{seed}'])
            for key in ('balanced_accuracy','macro_f1'):
                np.testing.assert_allclose(actual[key],expected[key],atol=1e-12,rtol=0)
            assert actual['confusion_matrix']==expected['confusion_matrix']
            scores.append(actual['balanced_accuracy']); prediction_count+=len(pred['labels'])
        recomputed.setdefault('EEGNet5',[]).append(float(np.mean(scores)))
    for name,values in recomputed.items():
        np.testing.assert_allclose(np.mean(values),results['summary'][name]['mean_balanced_accuracy'],atol=1e-12,rtol=0)
    source=json.loads((RUN/'source_snapshot.json').read_text(encoding='utf-8'))
    from mi_finger_data import HERE
    for name,digest in source.items():
        if sha256_file(HERE/name)!=digest: raise ValueError('Frozen source changed: '+name)
    scales=sorted(set(r['events']['onset_multiplier'] for r in audit['records']))
    write_json(RUN/'verification.json',dict(all_frozen_prediction_metrics_recomputed=True,
        total_prediction_labels_recomputed=prediction_count, all_split_disjoint_checks_passed=True,
        source_snapshot_unchanged=True, native_marker_samples_checked=native_samples,
        event_rows_checked=event_rows, event_onset_multipliers=scales,cues_by_task=marker_counts,
        counterbalance_contradicting_sidecar_count=len(contradictions),counterbalance_contradictions=contradictions,
        random_cue_sequences_unique=len({r['cue_sequence_sha256'] for r in audit['records'] if r['task']=='random'}),
        all_cues_six_seconds=all(i['duration_seconds']==6 for r in audit['records'] for i in r['intervals'] if 3<=i['code']<=7),
        results_sha256=sha256_file(RUN/'results.json'), protocol_sha256=sha256_file(RUN/'protocol.json'),
        data_audit_sha256=sha256_file(RUN/'data_audit.json'), board_accessed=False,control_enabled=False))
    print(f'VERIFIED {prediction_count} predictions; metadata conflicts {len(contradictions)}',flush=True)


if __name__=='__main__': main()

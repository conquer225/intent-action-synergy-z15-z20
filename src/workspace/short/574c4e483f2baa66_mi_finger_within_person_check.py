"""Post-hoc identifiability diagnostic, not cross-person validation or model selection."""
import torch
import json
import numpy as np
from mi_finger_baseline import fit_lda, metrics
from mi_finger_data import RUN, write_json, sha256_file


def main():
    protocol=json.loads((RUN/'protocol.json').read_text(encoding='utf-8'))
    diagnostic=dict(status='declared_after_main_baseline_before_this_check',
        purpose='Check whether the same fixed8 features transfer between random runs of one development person; never relabel as cross-person improvement',
        people=protocol['development_people'], directions=['run1_to_run2','run2_to_run1'],
        method='same bandpower/ERD shrinkage LDA; no tuning or score-based rejection',
        untouched_confirmation_people=protocol['confirmation_people'],
        main_results_sha256=sha256_file(RUN/'results.json'), control_enabled=False)
    write_json(RUN/'within_person_protocol.json',diagnostic)
    data=np.load(RUN/'development_trials.npz')
    x=data['features'].reshape(len(data['labels']),-1); rows=[]
    for person in diagnostic['people']:
        for first,second in ((1,2),(2,1)):
            train=(data['people']==person)&(data['run_number']==first)
            test=(data['people']==person)&(data['run_number']==second)
            guessed,_=fit_lda(x[train],data['labels'][train],x[test])
            rows.append(dict(person=person,fit_run=first,test_run=second,fit_trials=int(train.sum()),
                             **metrics(data['labels'][test],guessed)))
    means=[float(np.mean([r['balanced_accuracy'] for r in rows if r['person']==p])) for p in diagnostic['people']]
    report=dict(protocol_sha256=sha256_file(RUN/'within_person_protocol.json'),folds=rows,
                mean_person_balanced_accuracy=float(np.mean(means)),mean_direction_macro_f1=float(np.mean([r['macro_f1'] for r in rows])),
                no_cross_person_or_control_claim=True,confirmation_not_used=True,control_enabled=False)
    write_json(RUN/'within_person_results.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='folds'}),flush=True)


if __name__=='__main__': main()

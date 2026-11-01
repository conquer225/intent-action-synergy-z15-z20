"""Rebuild policy confusion matrices from exported predictions and verify frozen inputs."""
import csv
import json
import platform
from collections import defaultdict
from pathlib import Path

import numpy as np
from .emotion_baseline import sha256
from .compare_seed_gate_policies import OUTPUT, PREVIOUS


def main():
    protocol=json.loads((OUTPUT/'protocol.json').read_text())
    for path,digest in protocol['hashes'].items():
        assert sha256(Path(path))==digest,path
    records=sorted(OUTPUT.glob('*_20*.json'))
    assert len(records)==45
    total=0
    counts=defaultdict(lambda:{'sessions':0,'without_output':0,'first_output':[]})
    for path in records:
        record=json.loads(path.read_text())
        with path.with_suffix('.csv').open() as f:rows=list(csv.DictReader(f))
        for summary in record['results']:
            key=(summary['condition'],summary['policy'])
            selected=[r for r in rows if (r['condition'],r['policy'])==key]
            cm=np.zeros((3,3),int)
            for row in selected:
                cm[int(row['target'])+1,int(row['prediction'])+1]+=1
                if key[0]!='clean':
                    end=float(row['end_seconds'])
                    assert not (end>90 and end-12<94),'Prediction includes known injected fault'
            np.testing.assert_array_equal(cm,summary['cm'])
            total+=len(selected)
            assert sum(int(r['warning']) for r in selected)==summary['warning_predictions']
            counts[key]['sessions']+=1
            first=summary['first_output_seconds']
            if first is None:counts[key]['without_output']+=1
            else:counts[key]['first_output'].append(first)
    results=json.loads((OUTPUT/'results.json').read_text())
    primary={}
    for name,comparison in results['primary_comparisons'].items():
        ci=comparison['simultaneous_ci98333']
        margin=-.02 if comparison['metric']=='accepted_balanced_accuracy' else 0.
        primary[name]={'passes':ci is not None and ci[0]>margin,'lower_required':margin,**comparison}
    deviations={}
    for method,summary in results['methods'].items():
        deviations[method]={}
        for metric in ('accepted_balanced_accuracy','coverage','balanced_correct_output_yield'):
            values=[r[metric] for r in summary['participants']]
            deviations[method][metric]=None if None in values else float(np.std(values,ddof=1))
    audit={'frozen_hashes_verified':True,'csv_predictions_recounted':total,
           'new_policy_predictions_overlapping_known_faults':0,'primary_tests':primary,
           'participant_standard_deviations':deviations,
           'startup':{'_'.join(k):{'sessions':v['sessions'],'without_output':v['without_output'],
                                'median_first_output_seconds':float(np.median(v['first_output'])) if v['first_output'] else None} for k,v in counts.items()},
           'environment':{'python':platform.python_version(),'numpy':np.__version__,'platform':platform.platform()},
           'old_baselines':str(PREVIOUS),'board_changed':False}
    (OUTPUT/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps({'predictions':total,'primary_tests':primary},indent=2))


if __name__=='__main__':main()

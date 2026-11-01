"""Post-run consistency checks; does not select models or change thresholds."""
import csv
import json
import platform
from collections import Counter
from pathlib import Path

import numpy as np
import scipy
import sklearn

from .emotion_baseline import sha256
from .seed_gated_evaluation import CACHE, OUTPUT


def main():
    protocol = json.loads((OUTPUT/'protocol.json').read_text())
    for name, digest in protocol['hashes'].items():
        assert sha256(Path(name)) == digest, name
    with (CACHE/'predictions.csv').open() as f:
        baseline = {(int(r['subject']),int(r['session']),int(r['trial']),int(r['window'])):int(r['prediction'])
                    for r in csv.DictReader(f) if r['method']=='matched_adapt'}
    reproduced = {}
    sessions = []
    for path in sorted(OUTPUT.glob('*_20*.json')):
        sessions.append(json.loads(path.read_text()))
        with path.with_suffix('.csv').open() as f:
            for r in csv.DictReader(f):
                if r['condition']=='clean' and r['gated']=='0':
                    window = int((float(r['end_seconds'])-14)/12)
                    key = (int(r['subject']),int(r['session']),int(r['trial']),window)
                    assert key not in reproduced
                    reproduced[key] = int(r['prediction'])
    assert len(sessions)==45
    assert baseline == reproduced
    methods = {}
    for c in ('clean','flat','burst','gap'):
        for gated in (False,True):
            selected = [s for r in sessions for s in r['results'] if s['condition']==c and s['gated']==gated]
            counts, reasons = Counter(), Counter()
            for s in selected:
                counts.update(s['states']); reasons.update(s['reasons'])
            durations = np.sum([s['duration'] for s in selected],axis=0)
            cm = np.sum([s['cm'] for s in selected],axis=0)
            assert np.all(12*cm.sum(axis=1)<=durations)
            methods[c+('_gate' if gated else '_no_gate')] = {'states':dict(counts),'reasons':dict(reasons),
                'class_duration_seconds':durations.tolist(),'pooled_confusion_matrix':cm.tolist()}
    result = {'frozen_sources_verified':True,'baseline_predictions_exactly_reproduced':len(baseline),
              'environment': {'python':platform.python_version(),'numpy':np.__version__,
                              'scipy':scipy.__version__,'sklearn':sklearn.__version__,
                              'platform':platform.platform(),'processor':platform.processor()},
              'methods':methods}
    (OUTPUT/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()

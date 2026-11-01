"""Read-only gate attribution on two declared illustrative sessions; not tuning."""
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from threadpoolctl import threadpool_limits

from .emotion_baseline import sha256
from .seed_gated_evaluation import INITIAL, OUTPUT, INDICES, trial_names, to_simulated_250
import seed_quality_runtime as runtime
from cyton_sqi import CytonSQIMonitor, channel_sqi


class DiagnosticMonitor(CytonSQIMonitor):
    counts = Counter()

    def process(self, samples_uv, transport_ok=True):
        result = super().process(samples_uv, transport_ok)
        descriptors = channel_sqi(samples_uv)
        heuristic = self._heuristic_quality(descriptors)
        hard = (descriptors[:,2]>=.95)|(descriptors[:,3]>.001)
        for i, channel in enumerate(result['channels']):
            if channel['usable']:
                continue
            self.counts['bad_channel_decisions'] += 1
            if hard[i]:
                self.counts['hard_flat_or_clipping'] += 1
            elif heuristic[i]<.5:
                self.counts['absolute_heuristic'] += 1
            elif not channel['calibrated'] and result['calibrated']:
                self.counts['not_calibrated'] += 1
            else:
                self.counts['adaptive_only'] += 1
        return result


def main():
    manifest = json.loads((INITIAL/'manifest.json').read_text())
    reports = []
    # Process-local instrumentation only; board and source runtime remain unchanged.
    runtime.CytonSQIMonitor = DiagnosticMonitor
    with threadpool_limits(limits=1):
        for subject, session in [(1,'20131027'),(3,'20140603')]:
            record = next(r for r in manifest['records'] if r['subject']==subject and str(r['session'])==session)
            assert sha256(Path(record['path']))==record['sha256']
            raw = loadmat(record['path'])
            engine = runtime.SeedQualityRuntime(dict(np.load(OUTPUT/('fold_%02d.npz'%subject))))
            DiagnosticMonitor.counts = Counter()
            states = Counter()
            for name in trial_names(raw):
                engine._reset_signal()
                engine.pending = np.empty((0,8))
                values = to_simulated_250(raw[name][list(INDICES)].T)
                for start in range(0,len(values)//500*500,500):
                    states.update(e['state'] for e in engine.append(values[start:start+500]))
            original = json.loads((OUTPUT/(str(subject)+'_'+session+'.json')).read_text())
            expected = next(s['states'] for s in original['results'] if s['condition']=='clean' and s['gated'])
            assert states == expected
            reports.append({'subject':subject,'session':session,'states':dict(states),
                            'channel_attribution':dict(DiagnosticMonitor.counts)})
    (OUTPUT/'diagnostic.json').write_text(json.dumps({'scope':'Two illustrative sessions; not population estimate; no tuning',
        'instrumented_states_exactly_match':True,'sessions':reports},indent=2),encoding='utf-8')
    print(json.dumps(reports,indent=2))


if __name__ == '__main__':
    main()

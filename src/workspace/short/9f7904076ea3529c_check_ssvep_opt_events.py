"""Compare full event streams from staged baseline and candidate without score rounding."""
import json

import numpy as np

from stage_ssvep_opt_candidate import OUT


def main():
    baseline = json.loads((OUT/'bridge_baseline_events.json').read_text())
    candidate = json.loads((OUT/'bridge_candidate_events.json').read_text())
    if len(baseline) != len(candidate):
        raise AssertionError('Event count differs')
    maximum = 0.0
    for index, (old, new) in enumerate(zip(baseline, candidate)):
        for key in ('state','reason','window_start_index','window_end_index_exclusive',
                    'frequency_hz','target_index','quality','control_enabled','sequence_gaps'):
            if old[key] != new[key]:
                raise AssertionError(f'Event {index} differs in {key}')
        if old['scores'] is not None:
            np.testing.assert_allclose(old['scores'], new['scores'], atol=1e-9, rtol=1e-7)
            maximum = max(maximum, float(np.max(np.abs(np.asarray(old['scores'])-new['scores']))))
            np.testing.assert_allclose(old['margin'], new['margin'], atol=1e-9, rtol=1e-7)
    result = {'passed': True, 'events': len(baseline), 'maximum_score_absolute_error': maximum,
              'state_quality_window_identity_exact': True, 'score_atol': 1e-9,
              'score_rtol': 1e-7, 'source': 'non-wear bench, no accuracy claim'}
    (OUT/'event_parity.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()

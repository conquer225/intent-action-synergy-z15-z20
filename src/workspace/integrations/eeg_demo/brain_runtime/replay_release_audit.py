"""Replay-only observation of actual numerical calls and published endpoints.

No thresholds, weights, filters or prediction decisions are changed. Arrays are
copied in memory and written after replay, never to production status paths.
"""
from copy import deepcopy
import functools
import json
from pathlib import Path
import sys
import threading
import time

import numpy as np
import soak_service_replay as replay
from cyton_covariance import CovarianceFeatureStream, CovarianceSVM
from cyton_fatigue import FourChannelDEStream, FourChannelFatigue
from cyton_sqi import CausalEEGFilter
from seed_quality_runtime import SeedQualityRuntime
from seed_shadow import SeedShadow
from ssvep_core import CachedCCA
from ssvep_shadow import SSVEPShadow


def main():
    output = Path(sys.argv[sys.argv.index('--output') + 1]).resolve()
    started = time.monotonic()
    arrays, calls, publications = {}, [], []
    filter_objects = []
    capture_lock = threading.RLock()

    def record(task, **values):
        with capture_lock:
            entry = {'task': task}
            for key, value in values.items():
                name = f'{len(calls):05d}_{key}'
                arrays[name] = np.asarray(value).copy()
                entry[key] = name
            calls.append(entry)

    def wrap(owner, name, observer):
        original = getattr(owner, name)
        @functools.wraps(original)
        def observed(self, *args, **kwargs):
            return observer(original, self, *args, **kwargs)
        setattr(owner, name, observed)

    def filtered(original, self, values):
        with capture_lock:
            if not any(self is obj for obj in filter_objects):
                filter_objects.append(self)
            index = next(i for i, obj in enumerate(filter_objects) if obj is self)
        result = original(self, values)
        record('filter', instance=index, input=values, output=result)
        return result

    def covariance(original, self):
        result = original(self)
        record('covariance', bands=np.asarray([np.asarray(rows) for rows in self.rows]), output=result)
        return result

    def svm(original, self, feature):
        result = original(self, feature)
        record('emotion', input=feature, label=result[0], votes=result[1], scores=result[2])
        return result

    def de(original, self):
        result = original(self)
        if result is not None:
            record('de', ring=self.ring, output=result)
        return result

    def fatigue(original, self, values):
        result = original(self, values)
        record('fatigue', input=values, output=result)
        return result

    def seed(original, self, feature):
        mean = self.mean.copy()
        result = original(self, feature)
        if result['state'] == 'prediction':
            record('seed', input=feature, mean=mean, scores=result['scores'], label=result['class_id'])
        return result

    def cca(original, self, values):
        result = original(self, values)
        # Centered references preserve exactly the installed protocol.
        references = self.centered.transpose(0, 2, 1)
        if 'ssvep_references' not in arrays:
            arrays['ssvep_references'] = references.copy()
        elif not np.array_equal(arrays['ssvep_references'], references):
            raise AssertionError('Reference bank changed during fixed-protocol replay')
        with capture_lock:
            record('ssvep', input=values, regularization=self.regularization, output=result)
            calls[-1]['references'] = 'ssvep_references'
        return result

    def publication(task, value):
        publications.append({'task': task, 'elapsed_seconds': time.monotonic()-started,
                             'value': deepcopy(value)})

    primary = replay.live.publish_result
    def publish_primary(value, calibrated, path, *args, **kwargs):
        result = primary(value, calibrated, path, *args, **kwargs)
        publication('primary', json.loads(Path(path).read_text()))
        return result
    replay.live.publish_result = publish_primary

    def publish_seed(original, self, event):
        result = original(self, event)
        publication('seed', json.loads(self.path.read_text()))
        return result

    def publish_ssvep(original, self, event):
        result = original(self, event)
        publication('ssvep', event)
        return result

    wrap(CausalEEGFilter, 'process', filtered)
    wrap(CovarianceFeatureStream, 'feature', covariance)
    wrap(CovarianceSVM, 'predict_feature', svm)
    wrap(FourChannelDEStream, 'features', de)
    wrap(FourChannelFatigue, '_predict', fatigue)
    wrap(SeedQualityRuntime, '_accept_feature', seed)
    wrap(CachedCCA, 'scores', cca)
    wrap(SeedShadow, 'publish', publish_seed)
    wrap(SSVEPShadow, 'write_event', publish_ssvep)
    if '--allow-experimental-mi' in sys.argv:
        from mi_eegnet_rms import OfflineEEGNet
        def mi_logits(original, self, values):
            result = original(self, values)
            record('mi', input=values, output=result)
            return result
        wrap(OfflineEEGNet, 'logits', mi_logits)
    try:
        replay.main()
    finally:
        if output.is_dir():
            worker_calls=output/'mi-worker-calls.json'
            if '--allow-experimental-mi' in sys.argv and worker_calls.is_file():
                calls.extend(json.loads(worker_calls.read_text(encoding='utf-8')))
                with np.load(output/'mi-worker-calls.npz',allow_pickle=False) as worker_arrays:
                    for name in worker_arrays.files:
                        if name in arrays:
                            raise AssertionError('Worker audit key collision')
                        arrays[name]=worker_arrays[name].copy()
            (output/'numerical_calls.json').write_text(json.dumps(calls))
            (output/'publications.json').write_text(json.dumps(publications))
            # Avoid thousands of ARM compression operations after the timed loop.
            np.savez(output/'numerical_calls.npz', **arrays)


if __name__ == '__main__':
    main()

"""Opt-in, reversible taps on the existing Z15 classifier instances.

Attach while the acquisition loop is paused. No serial reader, filter,
calibration, network settings or actuator interfaces are created here.
"""
import uuid
import numpy as np
from .training import PREPROCESSORS


class FeatureTap:
    def __init__(self, publisher, *, source):
        self.publisher, self.source = publisher, source
        self.prefix = uuid.uuid4().hex
        self.bindings, self.windows = [], dict(emotion=0, fatigue=0)
        self.dropped, self.published, self.closed = 0, 0, False

    def _publish(self, task, values,reference=None):
        if self.closed: return
        self.windows[task] += 1
        try:
            accepted = self.publisher.offer_features(task, values,
                feature_version=PREPROCESSORS[task], source=self.source,
                window_id='%s:%s:%d' % (self.prefix, task, self.windows[task]),original_reference=reference)
            if accepted: self.published += 1
            else: self.dropped += 1
        except Exception:
            # Auxiliary transport failure must not enter the original control loop.
            self.dropped += 1

    def _bind(self, instance, name, wrapper):
        existing = instance.__dict__.get(name)
        had_override = name in instance.__dict__
        self.bindings.append((instance, name, had_override, existing))
        setattr(instance, name, wrapper)

    def attach(self, *, emotion=None, fatigue=None):
        if self.closed or self.bindings: raise RuntimeError('tap is already attached or closed')
        if emotion is not None:
            original = emotion._accept_feature
            def observe_emotion(features, _original=original):
                try: centered = np.asarray(features, dtype=float)-emotion.mean
                except Exception: centered = None
                result = _original(features)
                try:
                    if result.get('state') == 'prediction' and centered is not None:
                        reference=None
                        if result.get('scores') is not None:
                            reference=dict(kind='SEED_linear',class_id=int(result['class_id'])+1,scores=result['scores'])
                        self._publish('emotion', centered,reference)
                except Exception:self.dropped+=1
                return result
            self._bind(emotion, '_accept_feature', observe_emotion)
        if fatigue is not None:
            original = fatigue._predict
            def observe_fatigue(features, _original=original):
                result = _original(features)
                try:
                    thresholds=getattr(fatigue,'model',{}).get('thresholds',[.35,.70])
                    reference=dict(kind='HGB_regressor',class_id=int(np.searchsorted(thresholds,result,side='right')),value=float(result))
                    self._publish('fatigue', features,reference)
                except Exception:self.dropped+=1
                return result
            self._bind(fatigue, '_predict', observe_fatigue)
        return self

    def close(self):
        self.closed = True
        for instance, name, had_override, existing in reversed(self.bindings):
            if had_override: setattr(instance, name, existing)
            else: delattr(instance, name)
        self.bindings.clear()

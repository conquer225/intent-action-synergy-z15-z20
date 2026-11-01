"""Offline-only policy ablation; never imported by the live acquisition service."""
from copy import deepcopy

import numpy as np

from seed_quality_runtime import SeedQualityRuntime
from cyton_sqi import channel_sqi


class GatePolicy(SeedQualityRuntime):
    def __init__(self, weights, soft_warning=False, retain_short_gap=False):
        self.soft_warning = soft_warning
        self.retain_short_gap = retain_short_gap
        self.clock_seconds = 0.
        super().__init__(weights)

    def _reset_signal(self):
        super()._reset_signal()
        self.window_warning = False

    def reset(self):
        super().reset()
        self.last_trusted_seconds = None

    def begin_trial(self):
        self._reset_signal()
        self.pending = np.empty((0,8))
        # Missing inter-film rest cannot establish baseline freshness.
        self.last_trusted_seconds = None

    def gap(self, seconds, same_stream=True):
        retain = (self.retain_short_gap and same_stream and 0 < seconds <= 5
                  and self.accepted_windows >= 5 and np.isfinite(self.mean).all()
                  and self.last_trusted_seconds is not None
                  and self.clock_seconds + seconds - self.last_trusted_seconds <= 30)
        mean, count, sqi, stamp = self.mean.copy(), self.accepted_windows, self.sqi, self.last_trusted_seconds
        self.clock_seconds += seconds
        self.reset()
        if retain:
            self.mean, self.accepted_windows, self.sqi = mean, count, sqi
            self.last_trusted_seconds = stamp
        return self._event('reset', baseline_retained=bool(retain))

    def _accept_feature(self, feature):
        if self.soft_warning and self.window_warning:
            self.window_warning = False
            if not np.isfinite(feature).all():
                return self.disconnect('invalid_feature')
            if self.accepted_windows < 5:
                return self._event('calibrating', warning=True, baseline_updated=False)
            scores = self.weight @ (feature-self.mean)+self.bias
            self.last_prediction = int(self.classes[np.argmax(scores)])
            return self._event('prediction', class_id=self.last_prediction, scores=scores.tolist(),
                               warning=True, baseline_updated=False)
        result = super()._accept_feature(feature)
        if result['state'] in ('calibrating','prediction'):
            self.last_trusted_seconds = self.clock_seconds
        return result

    def feed_block(self, raw):
        raw = np.asarray(raw, float)
        if raw.shape != (500,8):
            raise ValueError('Offline replay uses complete 2-second blocks')
        self.clock_seconds += 2
        if not self.soft_warning:
            events = super().append(raw)
            if any(e['state'] in ('rejected','reset') for e in events):
                self.last_trusted_seconds = None
            return events
        if not np.isfinite(raw).all():
            return [self.disconnect('nonfinite_input')]
        descriptors = channel_sqi(raw)
        self.raw_mains_ratio = descriptors[:,4].tolist()
        if np.any(descriptors[:,2]>=.95) or np.any(np.mean(np.abs(raw)>=.95*187500,axis=0)>.001):
            return self._reject('raw_flat_or_adc_rail')
        filtered = self.prefilter.process(raw)
        resampled = self.resampler.process(filtered)
        if self.warming:
            self.features.process(resampled)
            self.warming = False
            return [self._event('warming')]
        descriptors = channel_sqi(filtered)
        # Preserve all existing absolute engineering thresholds, not only flatline.
        if (np.any(descriptors[:,2]>=.95) or np.any(descriptors[:,3]>.001)
                or np.any(self.sqi._heuristic_quality(descriptors)<.5)):
            return self._reject('absolute_quality')
        proposal = deepcopy(self.sqi)
        quality = proposal.process(filtered)
        warning = quality['usable_channels'] != 8
        self.window_warning |= warning
        if not warning:
            self.sqi = proposal
        emitted = self.features.process(resampled)
        if not emitted:
            return [self._event('collecting',warning=warning)]
        return [self._accept_feature(feature) for feature in emitted]

    def _reject(self, reason):
        self.last_trusted_seconds = None
        self._reset_signal()
        return [self._event('rejected',reason=reason)]

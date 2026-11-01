"""Private recorded-EEG monitor; reuses deployed primary and SSVEP arithmetic."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from calibration_session import CalibrationSession
from cyton_guardianloop import (DEFAULT_CHANNEL_MAP, DEFAULT_UV_PER_COUNT, fatigue_payload)
from cyton_sqi import CausalEEGFilter, CytonSQIMonitor, primary_windows, segmented_sqi
from cyton_fatigue import FourChannelFatigue
from cyton_covariance import CovarianceFeatureStream, CovarianceSVM
from primary_window import PrimaryWindowProcessor
from cyton_trial_recorder import atomic_json


SOURCE = 'historical_recorded_eeg'
RECORDING = 'fe30199c0eb9fedb'


class PrimaryReplay:
    def __init__(self, models, calibration, output):
        self.output = Path(output)
        self.scale = DEFAULT_UV_PER_COUNT
        sqi = CytonSQIMonitor(calibration_windows=15, sample_rate_hz=250)
        fatigue = FourChannelFatigue(models/'cyton_fatigue_overlap4.json')
        model = CovarianceSVM(models/'gameemo_covariance_svm.npz')
        context = json.loads(calibration.read_text())['context']
        if tuple(context['channels']) != DEFAULT_CHANNEL_MAP or context['microvolts_per_count'] != self.scale:
            raise ValueError('Recorded calibration montage differs')
        for name, expected in context['models'].items():
            if hashlib.sha256((models/name).read_bytes()).hexdigest() != expected:
                raise ValueError('Recorded calibration model differs')
        if not CalibrationSession(calibration, context).load(sqi, fatigue):
            raise ValueError('Recorded calibration is not loadable')
        self.processor = PrimaryWindowProcessor(sqi, fatigue, model,
            CovarianceFeatureStream(DEFAULT_CHANNEL_MAP, storage='array'), None, None, None,
            DEFAULT_CHANNEL_MAP, self.scale, 'arm', primary_windows, segmented_sqi)
        self.filter = CausalEEGFilter(sample_rate_hz=250)
        self.offsets = None
        self.center = []
        self.pending = []
        self.samples = self.results = self.gaps = self.malformed = 0
        self.previous = None
        self.waveform = []
        self.publish(dict(valid=False, state='INVALID', reason='REPLAY_FEATURE_WARMUP',
            calibration_current=15, calibration_total=15, calibration_retained=True), None)

    def publish(self, result, due):
        payload = fatigue_payload(result, self.processor.calibration_ready)
        payload.update(source=SOURCE, real=False, offline=True, historical_eeg=True)
        if payload.get('emotion'):
            payload['emotion'] = dict(payload['emotion'], source=SOURCE, current_wearer=False)
        atomic_json(self.output, dict(source=SOURCE, recording_id=RECORDING, real=False,
            physical_output_enabled=False, current_wearer=False, fatigue=payload,
            updated_monotonic=time.monotonic(), latest_input_monotonic=due,
            processed_samples=self.samples, result_windows=self.results,
            waveform_uv=self.waveform[-125:]))

    def packet(self, values, sequence, malformed, due):
        counts = np.rint(np.asarray(values)/self.scale).astype(np.int32)
        gap = self.previous is not None and ((sequence-self.previous)&255) != 1
        self.previous = sequence
        self.samples += 1
        if gap or malformed:
            self.gaps += int(gap);self.malformed += int(bool(malformed))
            self.processor.reset_stream();self.filter.reset()
            self.offsets = None;self.center.clear();self.pending.clear()
            self.publish(dict(valid=False, state='INVALID', reason='RECORDED_STREAM_GAP',
                calibration_current=15, calibration_retained=True), due)
            return
        if self.offsets is None:
            self.center.append(counts)
            if len(self.center) < 25:
                return
            self.offsets = np.stack(self.center).mean(axis=0)
            self.pending.extend(self.center);self.center.clear()
        else:
            self.pending.append(counts)
        count = len(self.pending)//10*10
        if not count:
            return
        batch = np.asarray(self.pending[:count]);del self.pending[:count]
        clean = self.filter.process((batch-self.offsets)*self.scale)
        self.waveform.extend(clean.tolist())
        del self.waveform[:-125]
        counters = dict(packets_seen=self.samples, dropped_packets=0, sequence_gaps=self.gaps,
                        unresolved_gaps=0, malformed_bytes=self.malformed)
        for raw, filtered in zip(batch, clean):
            result = self.processor.append(raw, filtered, False, counters)
            if result is not None:
                self.results += 1
                if time.monotonic()-due > .5:
                    result.update(valid=False, state='INVALID', reason='REPLAY_COMPUTATION_STALE',
                                  emotion=dict(valid=False, state='replay_computation_stale'))
                self.publish(result, due)

    def close(self):
        self.publish(dict(valid=False, state='INVALID', reason='REPLAY_FINISHED',
            calibration_current=15, calibration_retained=True), None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--recording', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--calibration', type=Path, required=True)
    args = parser.parse_args()
    # The existing paced reader validates every recorded file before reading EEG.
    import replay_backend as backend
    output = Path('/dev/shm')/(args.root.name+'-historical-monitor.json')
    if args.root.resolve().parent != Path('/home/xilinx') or not args.root.name.startswith('gl-eye-history-'):
        raise ValueError('Use a private historical demonstration directory')
    primary = PrimaryReplay(args.models, args.calibration, output)
    original = backend.SSVEPShadow

    class PairedShadow(original):
        def packet(self, values, sequence, malformed, **kwargs):
            events = super().packet(values, sequence, malformed, **kwargs)
            primary.packet(values, sequence, malformed, kwargs['now'])
            return events

    backend.SSVEPShadow = PairedShadow
    try:
        backend.run(args.root, args.recording, args.audit)
    finally:
        primary.close()


if __name__ == '__main__':
    main()

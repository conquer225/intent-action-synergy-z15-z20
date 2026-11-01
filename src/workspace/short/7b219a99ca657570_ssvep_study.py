"""Frozen four-target/center-gaze collection plan, never a decoder input."""
import hashlib
import json
from pathlib import Path
import random
import secrets

from cyton_trial_recorder import atomic_json
from ssvep_free import MIN_SCORE, MIN_MARGIN, POLICY

CHANNELS = ['F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2']


class SSVEPStudy:
    def __init__(self, directory, clock):
        self.directory = Path(directory)
        self.clock = clock
        self.plan = None
        self.attempts = []
        self.pending = None

    def _save(self):
        atomic_json(self.directory/(self.plan['study_id']+'.json'),
                    dict(plan=self.plan, attempts=self.attempts))

    def _runtime_hashes(self):
        root = Path(__file__).resolve().parent
        return {name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                for name in ('ssvep_free.py', 'ssvep_core.py', 'ssvep_stream.py',
                             'cyton_sqi.py', 'ssvep_candidate_sos.npy', 'ssvep_causal_protocol.json')
                if (root/name).is_file()}

    def create(self):
        if self.plan and (self.pending is not None or len(self.attempts) < 20):
            raise ValueError('已有未结束的采集计划；不能覆盖或重新挑选确认数据')
        token, seed = secrets.token_hex(8), secrets.randbits(32)
        generator = random.Random(seed)
        rows = []
        for phase in ('calibration', 'confirmation'):
            block = secrets.token_hex(8)
            for repeat in range(2):
                labels = [8, 10, 12, 14, 0]
                generator.shuffle(labels)
                offset = len(rows)
                rows.extend(dict(index=offset+index, phase=phase, block_id=block,
                                 repeat=repeat+1, requested_hz=hz)
                            for index, hz in enumerate(labels))
        self.plan = dict(schema='ssvep-four-corner-study-v1', study_id=token, seed=seed,
            channel_map=CHANNELS, decoder_channels=['O1', 'O2'], sample_rate_hz=250,
            created_monotonic=self.clock(), trials=rows,
            stimulus_frequencies=[8, 10, 12, 14], trial_seconds=10,
            rest_condition='center_gaze_while_all_four_targets_flicker',
            label_provenance='requested_gaze_not_verified_eye_tracking',
            split_unit='separate_raw_recordings_and_phase_blocks_not_overlapping_windows',
            calibration_only_for_future_fitting=True, confirmation_must_not_tune=True,
            frozen_policy=dict(id=POLICY, min_score=MIN_SCORE, min_margin=MIN_MARGIN,
                               confirmation_samples=500),
            frozen_runtime_sha256=self._runtime_hashes(),
            optical_onset_measured=False, physical_control=False)
        self.plan['digest'] = hashlib.sha256(json.dumps(self.plan, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()
        self.attempts = []
        self.pending = None
        self._save()
        return self.snapshot()

    def context(self, study_id):
        if not self.plan or study_id != self.plan['study_id']:
            raise ValueError('采集计划标识不匹配')
        if self._runtime_hashes() != self.plan['frozen_runtime_sha256']:
            raise ValueError('计划建立后识别代码或滤波资产改变；不能混入独立确认')
        if self.pending is not None:
            raise ValueError('上一段原始录制尚未关闭')
        if len(self.attempts) >= len(self.plan['trials']):
            raise ValueError('独立采集计划已结束；不自动重测或调整门限')
        row = self.plan['trials'][len(self.attempts)]
        return dict(row, study_id=study_id, plan_digest=self.plan['digest'],
                    label_used_by_decoder=False)

    def reserve(self, context, raw_id):
        if any(a['raw_recording_id'] == raw_id for a in self.attempts):
            raise ValueError('校准与确认不能共用原始记录')
        self.pending = dict(context, raw_recording_id=raw_id, state='preparing',
                            reserved_monotonic=self.clock(), session_id=None,
                            presented_monotonic=None)
        self.attempts.append(self.pending)
        self._save()

    def attach(self, session_id):
        self.pending.update(state='recording', session_id=session_id)
        self._save()

    def presented(self):
        if self.pending and self.pending['presented_monotonic'] is None:
            self.pending['presented_monotonic'] = self.clock()
            self._save()

    def stopped(self, reason):
        if self.pending and 'stopped_monotonic' not in self.pending:
            self.pending.update(stopped_monotonic=self.clock(), stop_reason=reason)
            self._save()

    def finish(self, metadata):
        row = self.pending
        if row is None:
            return
        onset, end = row['presented_monotonic'], row.get('stopped_monotonic')
        exposure = max(0., end-onset) if onset is not None and end is not None else 0.
        row.update(state='closed', raw_state=metadata.get('state'),
                   samples=metadata.get('samples', 0), exposure_seconds=round(exposure, 3),
                   collection_complete=(metadata.get('state') == 'complete'
                       and metadata.get('trial_id') == row['raw_recording_id']
                       and metadata.get('samples', 0) >= 2000 and exposure >= 8.),
                   raw_integrity_verified=False,
                   labels_verified_by_eye_tracking=False)
        self.pending = None
        self._save()

    def snapshot(self):
        if self.plan is None:
            return dict(state='not_created', decoder_receives_labels=False)
        complete = self.pending is None and len(self.attempts) == 20
        next_row = (self.plan['trials'][len(self.attempts)]
                    if len(self.attempts) < 20 else None)
        return dict(state='complete' if complete else ('recording' if self.pending else 'ready'),
                    id=self.plan['study_id'], plan_digest=self.plan['digest'],
                    completed_attempts=sum(a['state'] == 'closed' for a in self.attempts),
                    total_attempts=20, current=self.pending or next_row,
                    trial_seconds=10, decoder_receives_labels=False,
                    thresholds_fitted=False, confirmation_independent_recordings=True)

"""One live calibration block and one frozen confirmation block; no actuators."""
import hashlib
import json
from pathlib import Path
import secrets
import time

import numpy as np

from mi_cued import CuedMISession, hard_quality, WINDOW_SAMPLES
from mi_eegnet_rms import OfflineEEGNet

MODEL_SHA256 = '363daf3b68da6e80495319052447ec83e06b9e3e327a1bd0ff9e6023a5b54221'


class PersonalReadout:
    def __init__(self):
        self.mean = self.scale = self.weight = None
        self.bias = None

    def fit(self, features, labels):
        if self.weight is not None:
            raise ValueError('Personal readout is already frozen')
        values, y = np.asarray(features), np.asarray(labels)
        if (values.shape != (len(y), 240) or not np.isfinite(values).all()
                or set(y.tolist()) != {-1, 1}
                or min(np.sum(y == -1), np.sum(y == 1)) < 5):
            raise ValueError('At least five valid calibration trials per class required')
        self.mean = values.mean(0)
        self.scale = np.maximum(values.std(0), 1e-6)
        z = (values - self.mean) / self.scale / np.sqrt(240)
        self.bias = float(y.mean())
        self.weight = z.T @ np.linalg.solve(z @ z.T + np.eye(len(y)), y - self.bias)

    def logits(self, features):
        if self.weight is None:
            raise ValueError('Calibration not fitted')
        z = (features - self.mean) / self.scale / np.sqrt(240)
        margin = z @ self.weight + self.bias
        return np.column_stack((-margin / 2, margin / 2))

    def arrays(self):
        return dict(mean=self.mean, scale=self.scale, weight=self.weight,
                    bias=np.array(self.bias), alpha=np.array(1.))


class StudyModel:
    def __init__(self, base):
        self.base, self.personal = base, PersonalReadout()
        self.latest = None
        self.use_personal = False

    def logits(self, waveforms):
        features = self.base.features(waveforms)
        source_logits = self.base.score_features(features)
        logits = self.personal.logits(features) if self.use_personal else source_logits
        self.latest = dict(filtered=waveforms[0].T.copy(), features=features[0].copy(),
                           source_logits=source_logits[0].copy(), logits=logits[0].copy())
        return logits


class PersonalStudySession(CuedMISession):
    def __init__(self, model, *, directory, source='live', clock=time.monotonic, log_path=None):
        self.directory = Path(directory)
        self.directory.mkdir(exist_ok=False, parents=True)
        self.phase = None
        self.records = []
        self.completed = {}
        self.order = []
        self.active_trial = None
        self.fatal_error = None
        self.sensor = np.empty((0, 8))
        self.sensor_sequences = np.empty(0, dtype=np.uint8)
        super().__init__(StudyModel(model), source=source, clock=clock,
                         log_path=log_path or self.directory / 'events.jsonl')
        self._write('manifest.json', dict(schema='mi-rms-personal-v1', channels=list(self.snapshot()['channels']),
                    source=source, model_sha256=MODEL_SHA256,
                    label_semantics='intended_kinesthetic_imagery_not_verified_physiology',
                    calibration_trials=12, confirmation_trials=12, alpha=1,
                    control_enabled=False, production_eligible=False))

    def _write(self, name, value):
        (self.directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                                    allow_nan=False) + '\n', encoding='utf-8')

    def feed(self, raw_uv, sequences, *, received_monotonic=None):
        with self.lock:
            previous = self.index
            if self.active_trial is not None:
                values = np.asarray(raw_uv)
                if (values.ndim == 2 and values.shape[1] == 8 and len(values) <= 250
                        and np.isfinite(values).all() and self.active_trial['captured'] < 2500):
                    self.active_trial['sensor_batches'].append(values.copy())
                    self.active_trial['sequence_batches'].append(np.asarray(sequences).copy())
                    self.active_trial['batch_stamps'].append(self.clock() if received_monotonic is None
                                                            else received_monotonic)
                    self.active_trial['captured'] += len(values)
            super().feed(raw_uv, sequences, received_monotonic=received_monotonic)
            if self.index == previous + len(raw_uv):
                self.sensor = np.concatenate((self.sensor, raw_uv))[-2000:]
                self.sensor_sequences = np.concatenate((self.sensor_sequences, sequences))[-2000:]
            return self.snapshot()

    def disconnect(self, reason='transport_disconnected'):
        with self.lock:
            super().disconnect(reason)
            self.sensor = np.empty((0, 8))
            self.sensor_sequences = np.empty(0, dtype=np.uint8)

    def quality(self):
        if len(self.raw) < WINDOW_SAMPLES:
            return dict(ready=False, reason='warmup_or_no_data', invalid_channels=[])
        sqi = hard_quality(self.raw[-WINDOW_SAMPLES:])
        bad = (sqi[:, 0] > 100) | (sqi[:, 1] >= .8) | (sqi[:, 2] > 0)
        return dict(ready=not bool(np.any(bad)), reason='signal_invalid' if np.any(bad) else 'hard_gates_pass',
                    invalid_channels=[name for name, invalid in zip(self.snapshot_channels(), bad) if invalid])

    @staticmethod
    def snapshot_channels():
        from mi_features import CHANNELS
        return CHANNELS

    def _begin(self, phase):
        if self.source != 'live':
            raise ValueError('Personal calibration requires explicit live input')
        if self.phase is not None or phase in self.completed or self.fatal_error:
            raise ValueError('Block already started, completed, or failed; no silent retries')
        if phase not in ('calibration', 'confirmation'):
            raise ValueError('Unknown study phase')
        if phase == 'calibration' and self.completed:
            raise ValueError('Calibration cannot follow confirmation')
        if phase == 'confirmation' and self.model.personal.weight is None:
            raise ValueError('Successful calibration required first')
        state = super().snapshot()
        if state['input_state'] != 'ready' or not self.quality()['ready']:
            raise ValueError('Fresh, warmed-up, hard-quality-passing input required')
        self.phase, self.records = phase, []
        self.order = np.random.default_rng(20261003 if phase == 'calibration' else 20261004).permutation(
            ['left'] * 6 + ['right'] * 6).tolist()
        self.model.use_personal = phase == 'confirmation'
        (self.directory / phase).mkdir()
        self._write(phase + '/plan.json', dict(order=self.order, seed=20261003 if phase == 'calibration'
                                             else 20261004, parameters_frozen=phase == 'confirmation'))
        self._log('study_begin', phase=phase, order=self.order)

    def _next(self):
        if self.phase is None or self.active_trial is not None or len(self.records) >= 12:
            raise ValueError('No next trial is available')
        self.model.latest = None
        state = super().command(dict(action='start', target=self.order[len(self.records)], virtual_control=False))
        self.active_trial = dict(id=state['id'], start=self.index, start_monotonic=self.clock(),
                                 ordinal=len(self.records) + 1, captured=0,
                                 sensor_batches=[], sequence_batches=[], batch_stamps=[])

    def _finish(self, *, aborted=False):
        if self.active_trial is None:
            raise ValueError('No active study trial')
        self._expire()
        trial, active = self.trial, self.active_trial
        result = trial['result']
        accepted = result is not None and trial['state'] == 'active' and not aborted
        record = dict(id=trial['id'], ordinal=active['ordinal'], target=trial['target'],
                      accepted=accepted, reason=trial['reason'] if not accepted else 'accepted',
                      start_monotonic=active['start_monotonic'], end_monotonic=self.clock(),
                      result=result if accepted else None, source_label=None)
        arrays = dict(sensor_uv=np.concatenate(active['sensor_batches']) if active['sensor_batches'] else np.empty((0, 8)),
                      sequences=np.concatenate(active['sequence_batches']) if active['sequence_batches'] else np.empty(0),
                      batch_received_monotonic=np.asarray(active['batch_stamps']),
                      batch_lengths=np.array([len(v) for v in active['sensor_batches']]),
                      sensor_first_stream_index=np.array(active['start']))
        if accepted:
            arrays.update(self.model.latest)
            record['source_label'] = ('left', 'right')[int(np.argmax(arrays['source_logits']))]
            offset = self.index - len(self.raw)
            a, b = result['window_start'] - offset, result['window_end_exclusive'] - offset
            arrays['conditioned_uv'] = self.raw[a:b].copy()
        name = self.phase + '/trial-%02d.npz' % active['ordinal']
        arrays['metadata'] = np.array(json.dumps(record, ensure_ascii=False, allow_nan=False))
        try:
            np.savez_compressed(self.directory / name, **arrays)
            record['array_file'] = name
            record['sha256'] = hashlib.sha256((self.directory / name).read_bytes()).hexdigest()
            self.records.append(record)
            self._write(self.phase + '/trials.json', self.records)
            self._log('study_trial_saved', phase=self.phase, **record)
        except OSError as error:
            self.fatal_error = str(error)
            self._reject('study_recording_failed', terminal=True)
            raise
        trial.update(state='stopped', result=None, reason='study_trial_saved')
        self._stop_virtual('study_no_control')
        self.active_trial = None
        if len(self.records) == 12 and not aborted:
            self._complete()

    def _complete(self):
        phase = self.phase
        valid = [r for r in self.records if r['accepted']]
        report = dict(phase=phase, attempted=12, accepted=len(valid), rejected=12 - len(valid),
                      valid_by_class={c: sum(r['target'] == c for r in valid) for c in ('left', 'right')},
                      correct_all_attempts=sum(r['accepted'] and r['result']['matches_cue'] for r in self.records),
                      control_enabled=False)
        if phase == 'calibration':
            if min(report['valid_by_class'].values()) >= 5:
                arrays = [np.load(self.directory / r['array_file'], allow_pickle=False) for r in valid]
                try:
                    self.model.personal.fit(np.stack([a['features'] for a in arrays]),
                                            [-1 if r['target'] == 'left' else 1 for r in valid])
                finally:
                    for array in arrays:
                        array.close()
                np.savez_compressed(self.directory / 'personal_readout.npz', **self.model.personal.arrays())
                report['readout_sha256'] = hashlib.sha256((self.directory / 'personal_readout.npz').read_bytes()).hexdigest()
                report['status'] = 'fitted_frozen'
            else:
                report['status'] = 'insufficient_quality_no_fit'
        else:
            report['status'] = 'confirmation_complete_no_promotion'
            report['accuracy_all_attempts'] = report['correct_all_attempts'] / 12
            report['accuracy_accepted'] = report['correct_all_attempts'] / len(valid) if valid else None
            report['source_correct_all_attempts'] = sum(r['source_label'] == r['target'] for r in valid)
            report['confusion'] = {c: {p: sum(r['target'] == c and (r['result']['label'] if r['accepted']
                else 'rejected') == p for r in self.records) for p in ('left', 'right', 'rejected')}
                for c in ('left', 'right')}
        self._write(phase + '/report.json', report)
        self.completed[phase] = report
        self.phase = None
        self._log('study_block_complete', **report)

    def command(self, request):
        with self.lock:
            action = request.get('action')
            if action == 'study_begin':
                self._begin(request.get('phase'))
            elif action == 'study_next':
                self._next()
            elif action == 'study_finish':
                if self.active_trial is None or request.get('id') != self.active_trial['id']:
                    raise ValueError('Unknown or old study trial ID')
                self._finish()
            elif action == 'study_abort':
                if self.phase is not None:
                    if self.active_trial:
                        self._reject('study_aborted', terminal=True)
                        self._finish(aborted=True)
                    report = dict(status='aborted', phase=self.phase, attempted=len(self.records),
                                  control_enabled=False)
                    self._write(self.phase + '/report.json', report)
                    self.completed[self.phase] = report
                    self.phase = None
            elif action in ('presented', 'heartbeat', 'stop'):
                return super().command(request)
            else:
                raise ValueError('Study-only entry; target and results are not accepted from HTTP')
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            state = super().snapshot()
            state['result'] = None
            state['study'] = dict(phase=self.phase, completed_trials=len(self.records), total=12,
                                 completed=self.completed, predictions_hidden=True,
                                 fatal_error=self.fatal_error, personal_fitted=self.model.personal.weight is not None,
                                 model_sha256=MODEL_SHA256)
            state['quality'] = self.quality()
            return state


def create_session(model_path, *, source, log_path):
    path = Path(model_path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError('RMS model checksum mismatch')
    if log_path is None:
        raise ValueError('Private recording directory required')
    directory = Path(log_path).parent / ('study-' + secrets.token_hex(8))
    return PersonalStudySession(OfflineEEGNet(path, allow_experimental=True), directory=directory,
                                source=source)

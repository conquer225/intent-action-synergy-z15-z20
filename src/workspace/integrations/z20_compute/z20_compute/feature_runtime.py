"""Bounded latest-feature execution, using local receipt time and session fencing.

One worker owns all classifier calls. View selection is independent of this
module, so it cannot reset the source's preprocessing or calibration windows.
"""
from collections import deque
import threading
import time
import uuid
import copy
import numpy as np

from .protocol import Message, validate
from .training import PREPROCESSORS
from .environment import EnvironmentStore


class FeatureRuntime:
    TTL = dict(emotion=30., fatigue=20., sound=3.)

    def __init__(self, models, *, backend=None, navigation=None, now=time.monotonic):
        self.models, self.backend, self.now = models, backend, now
        self.environment = EnvironmentStore(now)
        self.navigation = navigation
        self.session = uuid.uuid4().hex
        self.lock = threading.RLock()
        self.wake, self.stopped = threading.Event(), threading.Event()
        self.pending, self.outputs, self.entries = {}, deque(maxlen=16), {}
        self.remote_session, self.sequence, self.epoch, self.result_sequence = None, -1, 0, 0
        self.windows = deque(maxlen=128)
        self.local_sequence=0
        self.local_epochs={task:0 for task in self.TTL}
        self.counters = dict(accepted=0, rejected=0, replaced=0, expired=0, errors=0)
        self.thread = threading.Thread(target=self._work, name="z20-features", daemon=True)
        self.thread.start()

    def submit_features(self, message):
        validate(message)
        if message.kind != "features":
            raise ValueError("feature input required")
        with self.lock:
            if self.remote_session is None:
                self.remote_session = message.session
            task = message.body["task"]
            key = (task, message.body["window_id"])
            if (self.stopped.is_set() or message.session != self.remote_session
                    or message.sequence <= self.sequence or key in self.windows):
                self.counters["rejected"] += 1
                return False
            self.sequence = message.sequence
            self.windows.append(key)
            self.counters["accepted"] += 1
            if task in self.pending:
                self.counters["replaced"] += 1
            self.pending[task] = (message, self.now(), self.epoch, 'network')
            self.wake.set()
            return True

    def submit_local(self,task,vector,*,feature_version,window_id,source,valid=True,quality=1.,reason='ok'):
        with self.lock:
            if self.stopped.is_set():return False
            self.local_sequence+=1
            message=Message('features',self.session,self.local_sequence,time.time_ns(),
                dict(task=task,vector=None if vector is None else np.asarray(vector).tolist(),
                     feature_version=feature_version,window_id=window_id,source=source,
                     valid=valid,quality=quality,reason=reason))
            validate(message)
            if task in self.pending:self.counters['replaced']+=1
            self.pending[task]=(message,self.now(),self.local_epochs[task],'local')
            self.counters['accepted']+=1;self.wake.set()
            return True

    def invalidate_local(self,task,*,reason='sample_changed'):
        with self.lock:
            self.local_epochs[task]+=1
            self.pending.pop(task,None)
            message=Message('features',self.session,self.local_sequence,time.time_ns(),
                dict(task=task,feature_version=PREPROCESSORS[task],window_id='local:pending',
                     source='recorded:board_file',quality=0.,valid=False,reason=reason,vector=None))
            body=self._result(message,reason);body['origin']='local'
            self.entries[task]=(body,self.now());self._emit(body)

    def publish_environment(self,body):
        with self.lock:
            if self.stopped.is_set():return False
            self.environment.put(body)
            self._emit(body,kind='environment')
            return True

    def environment_status(self):
        with self.lock:
            for body in self.environment.expire():self._emit(body,kind='environment')
            return self.environment.snapshot()

    def publish_snapshot(self):
        """New clients receive current local/static states; receipt ages stay intact."""
        with self.lock:
            self._expire();self.environment.expire()
            for body,_ in self.entries.values():self._emit(body)
            for body,_ in self.environment.entries.values():self._emit(body,kind='environment')

    def apply_key(self, event):
        if self.navigation is None:
            raise ValueError("navigation is not attached")
        with self.lock:
            self.navigation.apply(event)

    def _result(self, message, state, prediction=None):
        incoming = message.body
        valid = prediction is not None and prediction.valid
        return dict(task=incoming["task"], valid=valid, state=state,
            class_id=prediction.class_id if valid else None,
            scores=prediction.scores.tolist() if valid else None,
            model_version=prediction.model_version if prediction else
                getattr(self.models.get(incoming["task"]), "version", "unavailable"),
            backend=prediction.backend if prediction else "unavailable",
            window_id=incoming["window_id"], input_sequence=message.sequence,
            input_session=message.session, source=incoming["source"],
            quality=incoming["quality"], feature_version=incoming["feature_version"],
            original_reference=incoming.get('original_reference') if valid else None,
            reason=state)

    def _emit(self, body, *, kind='result'):
        self.result_sequence += 1
        self.outputs.append(Message(kind, self.session, self.result_sequence, time.time_ns(), copy.deepcopy(body)))

    def _work(self):
        while not self.stopped.is_set():
            self.wake.wait(.1)
            with self.lock:
                if not self.pending:
                    self.wake.clear()
                    continue
                task = next(iter(self.pending))
                message, received, epoch, origin = self.pending.pop(task)
            incoming = message.body
            prediction = None
            comparison = {}
            try:
                if self.now() - received > self.TTL[task]:
                    state = "expired"
                elif not incoming["valid"] or incoming["quality"] <= 0:
                    state = incoming["reason"] if not incoming["valid"] else "bad_quality"
                elif incoming["feature_version"] != PREPROCESSORS[task]:
                    state = "feature_version_mismatch"
                elif task not in self.models:
                    state = "model_unavailable"
                else:
                    started=time.perf_counter()
                    prediction = self.models[task].predict(incoming["vector"], backend=self.backend)
                    predict_seconds=time.perf_counter()-started
                    state = prediction.state
                    comparison['features']=list(incoming['vector'])
                    quantize=getattr(self.models[task],'quantize_input',None)
                    if quantize is not None:comparison['quantized_features']=quantize(incoming['vector']).tolist()
                    if self.backend is not None:
                        timing=dict(getattr(self.backend,'last_timing',{}))
                        started=time.perf_counter()
                        reference = self.models[task].predict(incoming["vector"], backend=None)
                        software_seconds=time.perf_counter()-started
                        timing.update(npu_predict_seconds=predict_seconds,software_seconds=software_seconds,
                            speedup=software_seconds/predict_seconds if predict_seconds>0 else None,
                            comparison_scope='same input quantization and integer prediction; excludes network and acquisition')
                        comparison['timing']=timing
                        equal = bool(np.array_equal(reference.scores, prediction.scores))
                        comparison.update(ps_scores=reference.scores.tolist(), ps_class_id=reference.class_id,
                                          integer_reference_equal=equal)
                        if not equal:
                            state, prediction = "integer_reference_mismatch", None
            except Exception as exc:
                state = "inference_error:" + type(exc).__name__
                with self.lock:
                    self.counters["errors"] += 1
            with self.lock:
                if (origin=='network' and epoch != self.epoch) or self.stopped.is_set():
                    continue
                if origin=='local' and epoch!=self.local_epochs[task]:continue
                if self.now() - received > self.TTL[task]:
                    state, prediction = "expired", None
                # A newer accepted window fences a slow computation immediately.
                if task in self.pending:
                    continue
                body = self._result(message, state, prediction)
                body['origin']=origin
                body['completed_monotonic']=self.now()
                body.update(comparison)
                self.entries[task] = (body, received)
                self._emit(body)

    def _expire(self):
        for task, (body, received) in list(self.entries.items()):
            if self.now() - received > self.TTL[task] and body["state"] not in ("expired", "disconnected"):
                body.update(valid=False, state="expired", reason="expired", class_id=None, scores=None,
                            ps_class_id=None, ps_scores=None,original_reference=None)
                self.counters["expired"] += 1
                self._emit(body)

    def poll(self):
        with self.lock:
            self._expire()
            for body in self.environment.expire():self._emit(body,kind='environment')
            messages = {}
            for message in self.outputs:
                task = message.body['task']
                current = (self.environment.entries if message.kind=='environment' else self.entries).get(task)
                keys=('frame_id','valid','state') if message.kind=='environment' else ('window_id','input_session','valid','state')
                if current is not None and all(message.body.get(key) == current[0].get(key) for key in keys):
                    messages[task] = message
            self.outputs.clear()
            return sorted(messages.values(), key=lambda message: message.sequence)

    def status(self):
        with self.lock:
            self._expire()
            return {task: dict(self.entries[task][0], age_seconds=max(0., self.now()-self.entries[task][1])) if task in self.entries else
                    dict(task=task, valid=False, state="waiting_input", class_id=None, scores=None)
                    for task in self.TTL}

    def disconnect_eeg(self):
        with self.lock:
            self.epoch += 1
            self.remote_session, self.sequence = None, -1
            self.windows.clear()
            self.pending={task:value for task,value in self.pending.items() if value[3]=='local'}
            self.outputs=deque((m for m in self.outputs if m.kind=='environment' or m.body.get('origin')=='local'),maxlen=16)
            for body, _ in self.entries.values():
                if body.get('origin')=='local':continue
                body.update(valid=False, state="disconnected", reason="disconnected", class_id=None, scores=None,
                            ps_class_id=None, ps_scores=None,original_reference=None)

    def submit_eeg(self, message):
        # The legacy raw-EEG runtime is a separate opt-in entry; it requires SciPy.
        raise ValueError("this endpoint requires classifier features; use the legacy raw-EEG service")

    def close(self):
        self.stopped.set(); self.wake.set()
        self.thread.join(3)
        if self.thread.is_alive():raise RuntimeError('classifier worker still owns the backend')
        self.disconnect_eeg()
        with self.lock:
            for body,_ in self.entries.values():
                body.update(valid=False,state='stopped',reason='stopped',class_id=None,scores=None,ps_class_id=None,ps_scores=None)
            for body,_ in self.environment.entries.values():
                body.update(valid=False,state='stopped',reason='stopped',payload=None)

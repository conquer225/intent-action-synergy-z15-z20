"""Compute sidecar coordination. Never owns capture, VDMA or HDMI lifecycle."""
import copy
import queue
import threading
import time
import uuid
from types import SimpleNamespace
import numpy as np
from .protocol import Message, TASKS, validate
from .video import AnalysisWorker
from .features import face_features
from .audio import sound_features


class RuntimeCoordinator:
    def __init__(self, *, models=None, eeg_adapter=None, backend=None, stereo=None, now=time.monotonic):
        self.models, self.eeg_adapter, self.backend = models or {}, eeg_adapter, backend
        self.now, self.session = now, uuid.uuid4().hex
        self.lock = threading.RLock()
        self.mode, self.audio_enabled = "idle", False
        self.entries, self.pending_results, self.sequence = {}, {}, 0
        self.ttl = dict(emotion=30., fatigue=20., face=2., sound=3., stereo=2.)
        self.stereo = stereo
        self.visual = AnalysisWorker(self._analyze_frame, now=now, ttl=2.)
        self.audio = AnalysisWorker(self._analyze_audio, now=now, ttl=3.)
        self.collected = {}
        self.eeg_epoch, self.eeg_reset = 0, False
        self.eeg_queue, self.stopped = queue.Queue(maxsize=8), threading.Event()
        self.eeg_thread = threading.Thread(target=self._eeg_loop, daemon=True, name="z20-eeg")
        self.eeg_thread.start()

    def _publish(self, task, captured_ns, *, prediction=None, state="invalid", values=None,
                 eeg_epoch=None, received_at=None):
        with self.lock:
            if eeg_epoch is not None and eeg_epoch != self.eeg_epoch:
                return
            valid = bool(prediction is not None and prediction.valid)
            self.sequence += 1
            body = dict(task=task, model_version=prediction.model_version if prediction is not None else "none",
                        valid=valid, class_id=prediction.class_id if valid else None,
                        scores=np.asarray(prediction.scores).tolist() if valid else None,
                        state=prediction.state if prediction is not None else state,
                        values=values or {})
            if prediction is not None:
                body["backend"] = prediction.backend
            message = Message("result", self.session, self.sequence, int(captured_ns), body)
            validate(message)
            self.entries[task] = (message, self.now() if received_at is None else received_at)
            self.pending_results[task] = message

    def _classify(self, task, features):
        model = self.models.get(task)
        return None if model is None else model.predict(features, backend=self.backend)

    def submit_eeg(self, message):
        validate(message)
        if message.kind != "eeg":
            raise ValueError("EEG record required")
        item = (copy.deepcopy(message), self.eeg_epoch)
        try:
            self.eeg_queue.put_nowait(item)
        except queue.Full:
            self.disconnect_eeg()
            return False
        return True

    def _eeg_loop(self):
        last_session = last_sequence = None
        last_epoch = self.eeg_epoch
        while not self.stopped.is_set():
            try:
                message, epoch = self.eeg_queue.get(timeout=.05)
            except queue.Empty:
                continue
            if epoch != self.eeg_epoch:
                continue
            if epoch != last_epoch:
                last_session = last_sequence = None
                last_epoch = epoch
            reset = self.eeg_reset or (last_session is not None and last_session != message.session)
            if last_session == message.session and last_sequence is not None:
                if message.sequence <= last_sequence:
                    continue
                reset |= message.sequence != last_sequence+1
            self.eeg_reset = False
            last_session, last_sequence = message.session, message.sequence
            try:
                if self.eeg_adapter is None:
                    for task in ("emotion", "fatigue"):
                        self._publish(task, message.captured_ns, state="eeg_adapter_unavailable", eeg_epoch=epoch)
                    continue
                if reset:
                    self.eeg_adapter.reset()
                samples = np.asarray(message.body["samples"], dtype=np.float64)
                for output in self.eeg_adapter.feed(samples):
                    task = output["task"]
                    prediction = self._classify(task, output["features"]) if output["valid"] else None
                    state = "model_unavailable" if output["valid"] and prediction is None else output["state"]
                    self._publish(task, message.captured_ns, prediction=prediction, state=state,
                                  values={"baseline": output.get("baseline", {})}, eeg_epoch=epoch)
            except Exception as exc:
                self.eeg_reset = True
                for task in ("emotion", "fatigue"):
                    self._publish(task, message.captured_ns, state=type(exc).__name__, eeg_epoch=epoch)

    def disconnect_eeg(self):
        with self.lock:
            self.eeg_epoch += 1
            self.eeg_reset = True
            while True:
                try:
                    self.eeg_queue.get_nowait()
                except queue.Empty:
                    break
            for task in ("emotion", "fatigue"):
                self._publish(task, time.time_ns(), state="eeg_disconnected")

    def set_mode(self, mode):
        if mode not in ("idle", "face", "stereo"):
            raise ValueError("unsupported frontend mode")
        with self.lock:
            if self.mode == mode:
                return
            self.mode = mode
            self.visual.invalidate()
            for task in ("face", "stereo"):
                self._publish(task, time.time_ns(), state="mode_changed")

    def submit_frame(self, frame, *, capture_mode, face_roi=None, distance_roi=None):
        """Accept an owned immutable snapshot; capture/display buffers stay external."""
        if frame.pixels.dtype != np.uint8 or frame.pixels.flags.writeable:
            raise ValueError("owned read-only uint8 snapshot required")
        with self.lock:
            if self.mode == "idle":
                return False
            return self.visual.submit(frame.sequence, (self.mode, frame, capture_mode, face_roi, distance_roi))

    def _analyze_frame(self, payload):
        task, frame, capture_mode, face_roi, distance_roi = payload
        prediction, values, state = None, {}, "model_unavailable"
        try:
            if task == "face":
                pixels = frame.pixels[0] if frame.pixels.shape[0] == 2 else frame.pixels
                prediction = self._classify("face", face_features(pixels, face_roi))
            elif self.stereo is None:
                state = "stereo_unavailable"
            else:
                if frame.pixels.ndim != 3 or frame.pixels.shape[0] != 2:
                    raise ValueError("stereo snapshot must contain two GRAY8 images")
                result = self.stereo.process(*frame.pixels, capture_mode=capture_mode, roi=distance_roi)
                valid = result.distance_m is not None
                prediction = SimpleNamespace(valid=valid, class_id=None, scores=None,
                        model_version="stereo-calibration-v1", backend="PS_StereoBM",
                        state="distance" if valid else "invalid_disparity")
                values = dict(distance_m=result.distance_m,
                              valid_pixels=int(np.count_nonzero(result.valid_mask)))
        except Exception as exc:
            state = type(exc).__name__
        return task, frame.captured_ns, prediction, state, values

    def set_audio(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("audio enable must be boolean")
        with self.lock:
            self.audio_enabled = enabled
            self.audio.invalidate()
            self._publish("sound", time.time_ns(), state="audio_enabled" if enabled else "audio_disabled")

    def submit_audio(self, sequence, captured_ns, pcm):
        with self.lock:
            if not self.audio_enabled:
                return False
            samples = np.asarray(pcm)
            if samples.shape != (16000,):
                raise ValueError("one second mono 16kHz audio required")
            owned = np.array(samples, dtype=np.float64, copy=True)
            owned.flags.writeable = False
            return self.audio.submit(sequence, (int(captured_ns), owned))

    def _analyze_audio(self, payload):
        captured_ns, pcm = payload
        prediction, state = None, "model_unavailable"
        try:
            prediction = self._classify("sound", sound_features(pcm))
        except Exception as exc:
            state = type(exc).__name__
        return "sound", captured_ns, prediction, state, {}

    def _collect(self):
        # Caller owns coordinator lock; mode switches and publication are atomic.
        for name, worker in (("visual", self.visual), ("audio", self.audio)):
            result = worker.result()
            if result is None or not result.valid:
                continue
            key = (result.epoch, result.sequence)
            if self.collected.get(name) == key:
                continue
            self.collected[name] = key
            task, captured_ns, prediction, state, values = result.value
            self._publish(task, captured_ns, prediction=prediction, state=state, values=values,
                          received_at=result.submitted_at)

    def poll(self):
        with self.lock:
            self._collect()
            for task, message in list(self.pending_results.items()):
                if message.body["valid"] and self.now()-self.entries[task][1] > self.ttl[task]:
                    self._publish(task, message.captured_ns, state="stale")
            messages = list(self.pending_results.values())
            self.pending_results.clear()
            return messages

    def status(self):
        with self.lock:
            self._collect()
            output = {}
            for task in TASKS:
                entry = self.entries.get(task)
                if entry is None:
                    output[task] = dict(valid=False, state="no_data", class_id=None, scores=None)
                elif self.now()-entry[1] > self.ttl[task]:
                    output[task] = dict(valid=False, state="stale", class_id=None, scores=None)
                else:
                    output[task] = copy.deepcopy(entry[0].body)
            return output

    def close(self):
        self.stopped.set()
        self.eeg_thread.join(2)
        self.disconnect_eeg()
        visual_closed = self.visual.close()
        audio_closed = self.audio.close()
        return not self.eeg_thread.is_alive() and visual_closed and audio_closed

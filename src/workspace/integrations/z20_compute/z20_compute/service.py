"""Opt-in bridge for an existing single EEG reader and a compute sidecar."""
import queue
import threading
import time
import numpy as np
from .link import SocketPeer, ResultCache
from .protocol import Message, CHANNELS


class BoardSession:
    def __init__(self, sock, runtime):
        self.runtime = runtime
        self.commands = queue.Queue(maxsize=16)
        self.command_sequence = -1
        self.peer = SocketPeer(sock, self._receive, self._disconnect, session=runtime.session)

    def _receive(self, message):
        if message.kind == "eeg":
            self.runtime.submit_eeg(message)
        elif message.kind == "features":
            self.runtime.submit_features(message)
        elif message.kind == "command" and message.sequence > self.command_sequence:
            self.command_sequence = message.sequence
            self.commands.put_nowait(message)

    def _disconnect(self, reason):
        self.runtime.disconnect_eeg()

    def start(self):
        snapshot=getattr(self.runtime,'publish_snapshot',None)
        if snapshot is not None:snapshot()
        self.peer.start()

    def pump(self):
        if self.peer.stopped.is_set():
            return False
        for _ in range(16):
            try:
                message = self.commands.get_nowait()
            except queue.Empty:
                break
            if message.body["op"] == "key_event":
                self.runtime.apply_key(message.body["event"])
            elif message.body["op"] == "set_mode":
                self.runtime.set_mode(message.body["mode"])
            else:
                self.runtime.set_audio(message.body["enabled"])
        for message in self.runtime.poll():
            self.peer.offer(message)
        return True

    def close(self):
        self.peer.close()


class EEGPublisher:
    """Call offer_samples after the original reader delivers calibrated microvolts.

    This class never opens a serial port, owns acquisition or alters Z15 state.
    Separate EEG/command counters prevent mode commands from creating EEG gaps.
    """
    def __init__(self, sock):
        self.results = ResultCache()
        self.lock = threading.Lock()
        self.eeg_sequence, self.command_sequence = 0, 0
        self.peer = SocketPeer(sock, self._receive, lambda reason: self.results.disconnect())

    def _receive(self, message):
        if self.results.session is None:
            self.results.connect(message.session)
        if message.kind in ("result", "environment"):
            self.results.accept(message)

    def start(self):
        self.peer.start()

    def offer_samples(self, samples, *, captured_ns=None):
        samples = np.asarray(samples)
        if samples.ndim != 2 or samples.shape[1] != 8 or not 1 <= len(samples) <= 250:
            raise ValueError("expected 1..250 samples by eight EEG channels in microvolts")
        with self.lock:
            self.eeg_sequence += 1
            return self.peer.offer(Message("eeg", self.peer.session, self.eeg_sequence,
                    time.time_ns() if captured_ns is None else int(captured_ns),
                    dict(sample_rate_hz=250, channels=list(CHANNELS), samples=samples.tolist())))

    def _command(self, body):
        with self.lock:
            self.command_sequence += 1
            return self.peer.offer(Message("command", self.peer.session, self.command_sequence, time.time_ns(), body))

    def set_mode(self, mode):
        return self._command(dict(op="set_mode", mode=mode))

    def set_audio(self, enabled):
        return self._command(dict(op="set_audio", enabled=enabled))

    def close(self):
        self.peer.close()


class FeaturePublisher(EEGPublisher):
    """Shared PC/Z15 publisher; features are tapped after original preprocessing."""
    def __init__(self, sock):
        super().__init__(sock)
        self.feature_sequence = 0

    def key_event(self, event):
        return self._command(dict(op="key_event", event=event))

    def offer_features(self, task, vector, *, feature_version, window_id, source,
                       valid=True, quality=1., reason="ok", captured_ns=None,original_reference=None):
        with self.lock:
            self.feature_sequence += 1
            body=dict(task=task, vector=None if vector is None else np.asarray(vector).tolist(),
                     feature_version=feature_version, window_id=window_id, source=source,
                     valid=valid, quality=quality, reason=reason)
            if original_reference is not None:body['original_reference']=original_reference
            return self.peer.offer(Message("features", self.peer.session, self.feature_sequence,
                time.time_ns() if captured_ns is None else int(captured_ns),body))


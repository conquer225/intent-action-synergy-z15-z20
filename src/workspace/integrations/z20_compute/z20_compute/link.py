"""Result lifetime is based on local receipt, independent of board clock skew."""
import threading
import time
import socket
import uuid
from collections import deque
from .protocol import Decoder, Message, encode, validate
from .environment import ENV_TTL


class ResultCache:
    def __init__(self, *, now=time.monotonic):
        self.now = now
        self.lock = threading.Lock()
        self.session = None
        self.entries = {}
        self.ttl = dict(face=2., stereo=2., sound=3., emotion=30., fatigue=20.)
        self.ttl.update(ENV_TTL)

    def connect(self, session):
        with self.lock:
            self.session = session
            self.entries.clear()

    def disconnect(self):
        self.connect(None)

    def accept(self, message, *, received_at=None):
        validate(message)
        with self.lock:
            if message.kind not in ("result", "environment") or self.session is None or message.session != self.session:
                return False
            task = message.body["task"]
            previous = self.entries.get(task)
            if previous is not None and message.sequence <= previous[0].sequence:
                return False
            self.entries[task] = (message, self.now() if received_at is None else received_at)
            return True

    def get(self, task, *, now=None):
        with self.lock:
            value = self.entries.get(task)
            if value is None:
                return None
            message, received_at = value
            if not message.body["valid"] or (self.now() if now is None else now) - received_at > self.ttl[task]:
                return None
            return message


class SocketPeer:
    """Bounded asynchronous I/O on an already connected private-lab socket.

    Callback work must enqueue, not perform inference. No commands can execute
    code, access paths, load models, or control actuators over this protocol.
    """
    def __init__(self, sock, on_message, on_disconnect, *, session=None, max_pending=8):
        if not 1 <= max_pending <= 128:
            raise ValueError("invalid transmit capacity")
        self.socket, self.on_message, self.on_disconnect = sock, on_message, on_disconnect
        self.session = session or uuid.uuid4().hex
        self.remote_session = None
        self.max_pending, self.pending = max_pending, deque()
        self.lock = threading.Lock()
        self.wake, self.stopped = threading.Event(), threading.Event()
        self.dropped, self.reason = 0, None
        self.threads = []
        self.socket.settimeout(.2)

    def offer(self, message):
        if message.session != self.session:
            raise ValueError("message belongs to another connection")
        wire = encode(message)
        if not self.lock.acquire(blocking=False):
            self.dropped += 1
            return False
        try:
            if self.stopped.is_set():
                return False
            if len(self.pending) >= self.max_pending:
                self.pending.popleft()
                self.dropped += 1
            self.pending.append(wire)
            self.wake.set()
            return True
        finally:
            self.lock.release()

    def start(self):
        if self.threads or self.stopped.is_set():
            raise RuntimeError("connection cannot be restarted")
        self.threads = [threading.Thread(target=f, daemon=True, name=name)
                        for f, name in [(self._receive, "z20-rx"), (self._transmit, "z20-tx")]]
        for thread in self.threads:
            thread.start()

    def _receive(self):
        decoder = Decoder()
        last_received = time.monotonic()
        partial_since = None
        try:
            while not self.stopped.is_set():
                now = time.monotonic()
                if now - last_received > 5 or (partial_since is not None and now - partial_since > 3):
                    raise TimeoutError("peer timeout")
                try:
                    data = self.socket.recv(16384)
                except socket.timeout:
                    continue
                if not data:
                    decoder.finish()
                    self._finish("eof")
                    return
                last_received = now
                for message in decoder.feed(data):
                    if self.remote_session is None:
                        self.remote_session = message.session
                    if message.session != self.remote_session:
                        raise ValueError("session changed within a connection")
                    self.on_message(message)
                if decoder.buffer:
                    if partial_since is None:
                        partial_since = now
                else:
                    partial_since = None
        except (OSError, ValueError, TypeError, TimeoutError) as exc:
            self._finish(type(exc).__name__)
        except Exception:
            self._finish("callback_error")

    def _transmit(self):
        next_ping, sequence = time.monotonic() + 1, 0
        try:
            while not self.stopped.is_set():
                self.wake.wait(.1)
                with self.lock:
                    wire = self.pending.popleft() if self.pending else None
                    if not self.pending:
                        self.wake.clear()
                if wire is None and time.monotonic() >= next_ping:
                    wire = encode(Message("ping", self.session, sequence, time.time_ns(), {}))
                    sequence += 1
                    next_ping = time.monotonic() + 1
                if wire is not None:
                    self.socket.sendall(wire)
        except OSError as exc:
            self._finish(type(exc).__name__)

    def _finish(self, reason):
        with self.lock:
            if self.stopped.is_set():
                return
            self.reason = reason
            self.stopped.set()
            self.pending.clear()
            self.wake.set()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()
        self.on_disconnect(reason)

    def close(self):
        self._finish("closed")
        for thread in self.threads:
            if thread is not threading.current_thread():
                thread.join(1)

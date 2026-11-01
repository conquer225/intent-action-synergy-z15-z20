"""Persistent, fail-closed TCP client for MultiControlS3 (Python standard library).

Use ``with ControlClient(host) as client`` so exceptions close the lease.  There is
no automatic reconnect or command retry.  Firmware remains the authority for
mode, enable, lease and hardware interlocks.
"""
from __future__ import annotations

import argparse
import json
import queue
import select
import shlex
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 1
DEFAULT_PORT = 9000
MAX_FRAME_BYTES = 1024  # Includes the final LF.
SOURCES = frozenset(("pc", "eye", "brain"))
DEVICES = frozenset(("hand", "pendulum", "all"))
ACTIONS = frozenset(("hello", "heartbeat", "status", "mode", "enable", "disable",
                     "estop", "open", "close", "pose", "start", "stop", "left", "right", "input", "zero"))


class ClientError(Exception):
    """A connection, framing or protocol error; reconnect must be explicit."""


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def validate_command(device: str, action: str, **fields: Any) -> dict[str, Any]:
    """Validate a request before a connection can transmit it."""
    if not isinstance(device, str) or not isinstance(action, str) \
            or device not in DEVICES or action not in ACTIONS:
        raise ValueError("unknown device or action")
    if set(fields) - {"mode", "angles", "input"}:
        raise ValueError("only mode, angles and input are optional command fields")
    if action in ("hello", "heartbeat") and device != "all":
        raise ValueError("hello/heartbeat require device=all")
    if device == "all" and action not in ("hello", "heartbeat", "status", "disable", "estop"):
        raise ValueError("choose hand or pendulum for this action")
    if action in ("open", "close", "pose") and device != "hand":
        raise ValueError("open/close/pose require device=hand")
    if action in ("start", "stop", "left", "right", "zero") and device != "pendulum":
        raise ValueError("start/stop/left/right require device=pendulum")
    if action == "mode":
        allowed = ("network", "emg", "glove") if device == "hand" else ("network", "emg", "tilt_test")
        if fields.get("mode") not in allowed or "angles" in fields or "input" in fields:
            raise ValueError(f"mode must be one of {allowed}")
    elif "mode" in fields:
        raise ValueError("mode is only valid for action=mode")
    if action == "pose":
        angles = fields.get("angles")
        if not isinstance(angles, list) or len(angles) != 6 or any(
                type(angle) is not int or not 0 <= angle <= 180 for angle in angles):
            raise ValueError("pose requires six integer angles in 0..180")
    elif "angles" in fields:
        raise ValueError("angles are only valid for action=pose")
    if action == "input":
        if device != "hand" or fields.get("input") not in ("contact", "rms"):
            raise ValueError("input requires hand and contact/rms")
    elif "input" in fields:
        raise ValueError("input is only valid for action=input")
    return {"device": device, "action": action, **fields}


def encode_frame(packet: dict[str, Any]) -> bytes:
    data = json.dumps(packet, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8") + b"\n"
    if len(data) > MAX_FRAME_BYTES:
        raise ValueError("JSON frame exceeds 1024 bytes including LF")
    return data


@dataclass
class _Pending:
    deadline: float
    automatic: bool = False
    event: threading.Event = field(default_factory=threading.Event)
    response: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class _Session:
    sock: socket.socket
    lock: threading.RLock = field(default_factory=threading.RLock)
    stop: threading.Event = field(default_factory=threading.Event)
    pending: dict[int, _Pending] = field(default_factory=dict)
    next_seq: int = 1
    greeted: bool = False
    thread: threading.Thread | None = None


class ControlClient:
    """One manually opened session with ACK-checked heartbeats and commands."""

    def __init__(self, host: str, port: int = DEFAULT_PORT, source: str = "pc", *,
                 heartbeat_interval: float = 0.1, ack_timeout: float = 0.35):
        if not isinstance(source, str) or source not in SOURCES:
            raise ValueError("source must be pc, eye or brain")
        if not 0.02 <= heartbeat_interval <= 0.15:
            raise ValueError("heartbeat interval must be between 20 and 150 ms")
        if not heartbeat_interval < ack_timeout < 0.5:
            raise ValueError("ACK timeout must exceed heartbeat interval and be below 500 ms")
        if not isinstance(host, str) or not host.strip() or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("host and TCP port are required")
        self.host, self.port, self.source = host, port, source
        self.heartbeat_interval, self.ack_timeout = heartbeat_interval, ack_timeout
        self._session: _Session | None = None
        self._lifecycle_lock = threading.RLock()
        self._status_lock = threading.Lock()
        self._latest_status: dict[str, Any] = {}
        self._last_error: str | None = None
        self.events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)

    @property
    def connected(self) -> bool:
        session = self._session
        return session is not None and session.greeted and not session.stop.is_set()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def latest_status(self) -> dict[str, Any]:
        with self._status_lock:
            return json.loads(json.dumps(self._latest_status))

    def _emit(self, event: dict[str, Any]) -> None:
        try:
            self.events.put_nowait(event)
        except queue.Full:
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            try:
                self.events.put_nowait(event)
            except queue.Full:
                pass

    def connect(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            if self.connected:
                raise ClientError("already connected")
            self.close(safe_stop=False)
            self._last_error = None
            with self._status_lock:
                self._latest_status = {}
            try:
                sock = socket.create_connection((self.host, self.port), timeout=2.0)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.settimeout(self.ack_timeout)
            except OSError as exc:
                self._last_error = f"connect failed: {exc}"
                raise ClientError(self._last_error) from exc
            session = self._session = _Session(sock)
            session.thread = threading.Thread(target=self._run, args=(session,),
                                              name="control-client-io", daemon=True)
            session.thread.start()
            try:
                reply = self._request(session, "all", "hello")
                if not reply["ok"]:
                    raise ClientError(f"hello rejected: {reply.get('error', 'unknown')}")
                with session.lock:
                    session.greeted = True
                self._emit({"event": "connected", "host": self.host, "port": self.port})
                return reply
            except (ClientError, OSError):
                self.close(safe_stop=False)
                raise

    def send(self, device: str, action: str, **fields: Any) -> dict[str, Any]:
        validate_command(device, action, **fields)
        session = self._session
        if session is None or not self.connected:
            raise ClientError("disconnected; connect and enable manually")
        if action in ("hello", "heartbeat"):
            raise ValueError("hello/heartbeat are managed by the client")
        return self._request(session, device, action, **fields)

    def _transmit(self, session: _Session, device: str, action: str, *,
                  automatic: bool = False, timeout: float | None = None,
                  **fields: Any) -> _Pending:
        command = validate_command(device, action, **fields)
        with session.lock:
            if session.stop.is_set():
                raise ClientError("connection is closed")
            if session.next_seq > 0xFFFFFFFF:
                self._abort(session, "sequence exhausted; reconnect manually")
                raise ClientError("sequence exhausted")
            seq = session.next_seq
            frame = encode_frame({"v": PROTOCOL_VERSION, "source": self.source,
                                  "seq": seq, **command})
            session.next_seq += 1
            pending = _Pending(time.monotonic() + (timeout or self.ack_timeout), automatic)
            session.pending[seq] = pending
            try:
                session.sock.sendall(frame)
            except OSError as exc:
                self._abort(session, f"send failed: {exc}")
                raise ClientError(f"send failed: {exc}") from exc
            return pending

    def _request(self, session: _Session, device: str, action: str, *,
                 timeout: float | None = None, **fields: Any) -> dict[str, Any]:
        pending = self._transmit(session, device, action, timeout=timeout, **fields)
        if not pending.event.wait((timeout or self.ack_timeout) + 0.1):
            self._abort(session, "ACK timeout")
        if pending.error or pending.response is None:
            raise ClientError(pending.error or "ACK timeout")
        return pending.response

    def _abort(self, session: _Session, reason: str) -> None:
        with session.lock:
            if session.stop.is_set():
                return
            session.stop.set()
            session.greeted = False
            self._last_error = reason
            for pending in session.pending.values():
                pending.error = reason
                pending.event.set()
            session.pending.clear()
            try:
                session.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            session.sock.close()
        self._emit({"event": "disconnected", "error": reason})

    def _receive_ack(self, session: _Session, line: bytes) -> None:
        try:
            ack = json.loads(line.decode("utf-8"), object_pairs_hook=strict_object,
                             parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (UnicodeError, ValueError) as exc:
            raise ClientError(f"invalid ACK JSON: {exc}") from exc
        if isinstance(ack, dict) and type(ack.get("v")) is int and ack["v"] == 1 \
                and ack.get("type") == "telemetry":
            if not isinstance(ack.get("status"), dict) or "seq" in ack:
                raise ClientError("invalid telemetry fields")
            with self._status_lock:
                self._latest_status = ack["status"]
            self._emit({"event": "telemetry", **ack})
            return
        if not isinstance(ack, dict) or type(ack.get("v")) is not int or ack["v"] != 1 \
                or type(ack.get("seq")) is not int or not 1 <= ack["seq"] <= 0xFFFFFFFF \
                or type(ack.get("ok")) is not bool:
            raise ClientError("invalid ACK fields")
        if "status" in ack and not isinstance(ack["status"], dict):
            raise ClientError("invalid ACK status")
        if "error" in ack and not isinstance(ack["error"], str):
            raise ClientError("invalid ACK error")
        with session.lock:
            pending = session.pending.pop(ack["seq"], None)
            if pending is None:
                raise ClientError("unexpected or duplicate ACK sequence")
            pending.response = ack
            pending.event.set()
        if "status" in ack:
            with self._status_lock:
                self._latest_status = ack["status"]
        if not pending.automatic or not ack["ok"]:
            self._emit({"event": "ack", **ack})
        if pending.automatic and not ack["ok"]:
            raise ClientError(f"heartbeat rejected: {ack.get('error', 'unknown')}")

    def _run(self, session: _Session) -> None:
        buffer = bytearray()
        next_heartbeat = time.monotonic() + self.heartbeat_interval
        try:
            while not session.stop.is_set():
                now = time.monotonic()
                with session.lock:
                    expired = any(p.deadline <= now for p in session.pending.values())
                    greeted = session.greeted
                if expired:
                    raise ClientError("ACK timeout; connection closed")
                if greeted and now >= next_heartbeat:
                    self._transmit(session, "all", "heartbeat", automatic=True)
                    next_heartbeat = now + self.heartbeat_interval
                readable, _, _ = select.select([session.sock], [], [], 0.02)
                if not readable:
                    continue
                chunk = session.sock.recv(2048)
                if not chunk:
                    raise ClientError("peer disconnected")
                buffer.extend(chunk)
                while b"\n" in buffer:
                    end = buffer.index(b"\n")
                    if end + 1 > MAX_FRAME_BYTES:
                        raise ClientError("ACK frame exceeds 1024 bytes")
                    line = bytes(buffer[:end])
                    del buffer[:end + 1]
                    self._receive_ack(session, line)
                if len(buffer) >= MAX_FRAME_BYTES:
                    raise ClientError("unterminated ACK frame exceeds limit")
        except (OSError, ValueError, ClientError) as exc:
            self._abort(session, str(exc))

    def close(self, *, safe_stop: bool = True) -> None:
        with self._lifecycle_lock:
            session = self._session
            if session is None:
                return
            if safe_stop and self.connected:
                try:
                    self._request(session, "all", "estop", timeout=0.2)
                except (OSError, ClientError):
                    pass
            self._abort(session, "client closed")
            if session.thread is not None and session.thread is not threading.current_thread():
                session.thread.join(timeout=1.0)
            self._session = None

    def __enter__(self) -> ControlClient:
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def parse_console_command(line: str) -> tuple[str, str, dict[str, Any]]:
    parts = shlex.split(line)
    if parts == ["status"]:
        return "all", "status", {}
    if parts in (["estop"], ["disable"]):
        return "all", parts[0], {}
    if len(parts) < 2:
        raise ValueError("use DEVICE ACTION [MODE / six angles]")
    device, action, *args = parts
    fields: dict[str, Any] = {}
    if action == "mode" and len(args) == 1:
        fields["mode"] = args[0]
    elif action == "input" and len(args) == 1:
        fields["input"] = args[0]
    elif action == "pose" and len(args) == 6:
        fields["angles"] = [int(value) for value in args]
    elif args:
        raise ValueError("unexpected command arguments")
    validate_command(device, action, **fields)
    return device, action, fields


def load_script(path: str | Path) -> list[dict[str, Any]]:
    """Prevalidate the whole rehearsal script before opening a TCP connection."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      object_pairs_hook=strict_object)
    if not isinstance(data, list):
        raise ValueError("script must be a JSON array")
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"script item {index + 1} must be an object")
        if set(item) == {"wait_ms"}:
            if type(item["wait_ms"]) is not int or not 0 <= item["wait_ms"] <= 60000:
                raise ValueError("wait_ms must be an integer in 0..60000")
            continue
        if not {"device", "action"} <= set(item):
            raise ValueError("each command needs device and action")
        validate_command(**item)
        if item["action"] in ("hello", "heartbeat"):
            raise ValueError("scripts must not send hello/heartbeat")
    return data


def run_script(client: ControlClient, steps: list[dict[str, Any]]) -> None:
    for item in steps:
        if "wait_ms" in item:
            deadline = time.monotonic() + item["wait_ms"] / 1000.0
            while time.monotonic() < deadline:
                if not client.connected:
                    raise ClientError(client.last_error or "disconnected during wait")
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            continue
        ack = client.send(**item)
        print(json.dumps(ack, ensure_ascii=False), flush=True)
        if not ack["ok"]:
            raise ClientError(f"script stopped on rejected command: {ack.get('error', 'unknown')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MultiControlS3 TCP control / local rehearsal")
    parser.add_argument("--host", help="ESP32 IPv4 address or hostname (required without --simulate)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--source", choices=sorted(SOURCES), default="pc")
    parser.add_argument("--script", help="JSON array of commands; failure stops the script")
    parser.add_argument("--simulate", action="store_true", help="use an in-process localhost simulator")
    args = parser.parse_args(argv)
    if not args.simulate and not args.host:
        parser.error("--host is required unless --simulate is used")
    if args.simulate and args.host:
        parser.error("--simulate cannot be combined with --host")
    try:
        steps = load_script(args.script) if args.script else None
        simulator = None
        if args.simulate:
            from mock_server import MockControlServer
            simulator = MockControlServer().start()
        host, port = ("127.0.0.1", simulator.port) if simulator else (args.host, args.port)
        try:
            with ControlClient(host, port, args.source) as client:
                if simulator:
                    print("SIMULATION: localhost only; no hardware output.")
                if steps is not None:
                    run_script(client, steps)
                else:
                    print("Connected. Commands: status; DEVICE mode MODE; DEVICE enable; "
                          "hand pose A B C D E F; hand open/close; pendulum start/stop/left/right; "
                          "estop; disable; quit")
                    while True:
                        try:
                            line = input("control> ").strip()
                        except EOFError:
                            break
                        if line in ("quit", "exit"):
                            break
                        if not line:
                            continue
                        try:
                            device, action, fields = parse_console_command(line)
                            print(json.dumps(client.send(device, action, **fields), ensure_ascii=False))
                        except ValueError as exc:
                            print(f"Invalid command: {exc}")
        finally:
            if simulator:
                simulator.close()
        return 0
    except (ClientError, OSError, ValueError) as exc:
        print(f"Stopped: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Stopped by user; connection closed.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

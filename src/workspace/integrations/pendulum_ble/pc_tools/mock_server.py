"""Local protocol rehearsal, deliberately bound to 127.0.0.1 only.

This validates session/mode behavior. It does not simulate STM32 control physics,
RF reliability, sensor calibration, actuator limits or hardware protection.
"""
from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from typing import Any

from pc_client import MAX_FRAME_BYTES, SOURCES, encode_frame, strict_object, validate_command


class MockControlServer:
    def __init__(self, port: int = 0, *, heartbeat_lease: float = 0.5,
                 telemetry_interval: float = 0.1, ack_heartbeats: bool = True):
        self.port = port
        self.heartbeat_lease = heartbeat_lease
        self.telemetry_interval = telemetry_interval
        self.ack_heartbeats = ack_heartbeats
        self.packets: list[dict[str, Any]] = []
        self.sessions_started = 0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._clients: set[socket.socket] = set()
        self._workers: list[threading.Thread] = []
        self._owners: dict[str, socket.socket] = {}
        self._state: dict[str, Any] = {
            "wifi": {"connected": True, "ip": "127.0.0.1"},
            "pendulum": {"mode": "emg", "source": "local", "enabled": False,
                         "bridge_link": True, "stm_fresh": True, "state": "stopped", "blocked": ""},
            "hand": {"mode": "emg", "source": "local", "enabled": False,
                     "pot_calibrated": True, "poses_ready": True, "pressure_calibrated": True,
                     "radio_ready": True, "radio_link": True, "pressure_valid": True,
                     "pressures": [0, 0, 0, 0, 0], "vibration_pwm": [0, 0, 0, 0, 0],
                     "angles": [90, 90, 90, 90, 90, 90], "actuator_ready": True},
            "sensors": {"strength": 0.0, "grip": False, "worn": True, "imu": True,
                        "swipe_ready": True, "side_g": 0.0, "emg_gaps": 0,
                        "pots": [2048, 2048, 2048, 2048, 2048, 2048]},
        }

    @property
    def status(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def start(self) -> MockControlServer:
        if self._listener:
            raise RuntimeError("simulator is already started")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.port))
        listener.listen(3)
        listener.settimeout(0.1)
        self._listener = listener
        self.port = listener.getsockname()[1]
        self._thread = threading.Thread(target=self._accept, name="mock-accept", daemon=True)
        self._thread.start()
        return self

    def _accept(self) -> None:
        assert self._listener is not None
        while not self._stop.is_set():
            try:
                sock, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self._lock:
                if len(self._clients) >= 3:
                    sock.close()
                    continue
                self._clients.add(sock)
                self.sessions_started += 1
            worker = threading.Thread(target=self._serve, args=(sock,), name="mock-session", daemon=True)
            self._workers.append(worker)
            worker.start()

    def _neutral(self, device: str) -> None:
        state = self._state[device]
        if device == "pendulum":
            state["state"] = "stopped"
        else:
            state["angles"] = [60] * 6  # Fixture OPEN, never a hardware recommendation.
            state["vibration_pwm"] = [0] * 5

    def _stop_owned(self, source: str) -> None:
        with self._lock:
            for device in ("hand", "pendulum"):
                state = self._state[device]
                if state["mode"] == "network" and state["source"] == source:
                    state["enabled"] = False
                    self._neutral(device)

    def _command(self, source: str, packet: dict[str, Any]) -> str | None:
        device, action = packet["device"], packet["action"]
        with self._lock:
            if action in ("hello", "heartbeat", "status"):
                return None
            if action in ("disable", "estop"):
                for target in (("hand", "pendulum") if device == "all" else (device,)):
                    self._state[target]["enabled"] = False
                    self._neutral(target)
                return None
            state = self._state[device]
            if action == "mode":
                if state["enabled"] and state["mode"] == "network" and state["source"] != source:
                    return "disable_before_takeover"
                state["mode"] = packet["mode"]
                state["source"] = source if packet["mode"] == "network" else "local"
                state["enabled"] = False
                self._neutral(device)
                return None
            if action == "enable":
                if state["mode"] == "network" and state["source"] != source:
                    return "source_not_owner"
                self._neutral(device)
                state["enabled"] = True
                return None
            if state["mode"] != "network":
                return "network_mode_required"
            if state["source"] != source:
                return "source_not_owner"
            if not state["enabled"]:
                return "disabled"
            if device == "hand":
                # Synthetic fixture poses. They are not real hardware presets.
                state["angles"] = (packet["angles"] if action == "pose" else
                                   [60] * 6 if action == "open" else [120] * 6)
                state["pressures"] = [100, 200, 300, 400, 500] if action == "close" else [0] * 5
                state["vibration_pwm"] = [25, 50, 75, 100, 125] if action == "close" else [0] * 5
            else:
                state["state"] = {"start": "balancing", "stop": "stopped",
                                  "left": "left", "right": "right"}[action]
            return None

    def _serve(self, sock: socket.socket) -> None:
        sock.settimeout(0.03)
        source: str | None = None
        previous_seq = 0
        lease = time.monotonic() + self.heartbeat_lease
        telemetry_at = time.monotonic() + self.telemetry_interval
        buffer = bytearray()
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if now >= lease:
                    return
                if source and self.telemetry_interval > 0 and now >= telemetry_at:
                    sock.sendall(encode_frame({"v": 1, "type": "telemetry", "status": self.status}))
                    telemetry_at = now + self.telemetry_interval
                try:
                    chunk = sock.recv(2048)
                except socket.timeout:
                    continue
                if not chunk:
                    return
                buffer.extend(chunk)
                while b"\n" in buffer:
                    end = buffer.index(b"\n")
                    if end + 1 > MAX_FRAME_BYTES:
                        return
                    raw = bytes(buffer[:end])
                    del buffer[:end + 1]
                    packet = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_object)
                    if not isinstance(packet, dict) or set(packet) - {
                            "v", "seq", "source", "device", "action", "mode", "angles"}:
                        return
                    if type(packet.get("v")) is not int or packet["v"] != 1 \
                            or type(packet.get("seq")) is not int \
                            or not previous_seq < packet["seq"] <= 0xFFFFFFFF \
                            or packet.get("source") not in SOURCES:
                        return
                    fields = {key: packet[key] for key in ("mode", "angles") if key in packet}
                    validate_command(packet.get("device"), packet.get("action"), **fields)
                    previous_seq = packet["seq"]
                    with self._lock:
                        self.packets.append(dict(packet))
                    error = None
                    if source is None:
                        if packet["action"] != "hello":
                            error = "hello_required"
                        else:
                            with self._lock:
                                if packet["source"] in self._owners:
                                    error = "source_busy"
                                else:
                                    source = packet["source"]
                                    self._owners[source] = sock
                    elif packet["source"] != source:
                        error = "source_changed"
                    elif packet["action"] == "hello":
                        error = "already_greeted"
                    if error is None and source:
                        if packet["action"] in ("hello", "heartbeat"):
                            lease = time.monotonic() + self.heartbeat_lease
                        error = self._command(source, packet)
                        if error is None:
                            lease = time.monotonic() + self.heartbeat_lease
                    ack = {"v": 1, "seq": packet["seq"], "ok": error is None, "error": error or ""}
                    if packet["action"] == "status" and error is None:
                        ack["status"] = self.status
                    if packet["action"] != "heartbeat" or self.ack_heartbeats:
                        sock.sendall(encode_frame(ack))
                    if error in ("source_busy", "hello_required", "source_changed"):
                        return
                if len(buffer) >= MAX_FRAME_BYTES:
                    return
        except (OSError, ValueError, TypeError):
            pass
        finally:
            with self._lock:
                if source:
                    self._stop_owned(source)
                    if self._owners.get(source) is sock:
                        del self._owners[source]
                self._clients.discard(sock)
            sock.close()

    def disconnect_all(self) -> None:
        with self._lock:
            clients = list(self._clients)
        for sock in clients:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def close(self) -> None:
        self._stop.set()
        self.disconnect_all()
        if self._listener:
            self._listener.close()
        if self._thread:
            self._thread.join(timeout=1)
        for worker in self._workers:
            worker.join(timeout=1)

    def __enter__(self) -> MockControlServer:
        return self.start()

    def __exit__(self, *_: Any) -> None:
        self.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Local TCP protocol simulator; no hardware control")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()
    with MockControlServer(args.port) as server:
        print(f"SIMULATION listening on 127.0.0.1:{server.port}; Ctrl+C to close.", flush=True)
        try:
            while True:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Independent finite Z15 eye-to-phone session; never configures PL or formal apps."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import threading
import time

from eye_gate import EyeGate
from network_receiver import NetworkReceiver, ReceiverError, load_config

NATIVE_SHA = "e5704d8e751801ee2223a5c8f6423005cc422a0473b83b03557b6c01e3d93fc7"
POINTS = ((.5, .5), (.15, .5), (.85, .5))


class PhoneSession:
    def __init__(self, config, native, directory):
        self.config, self.native, self.directory = config, Path(native), Path(directory)
        if hashlib.sha256(self.native.read_bytes()).hexdigest() != NATIVE_SHA:
            raise ValueError("Native eye sampler does not match the audited existing binary")
        self.receiver = NetworkReceiver(config)
        try:
            self.receiver_state = self.receiver.probe()
        except (OSError, ReceiverError):
            self.receiver.close()
            raise
        self.gate = EyeGate()
        self.lock = threading.RLock()
        self.worker = None
        self.reader_thread = None
        self.worker_log = None
        self.native_ready = self.trained = self.point_pending = False
        self.next_point = 0
        self.phase = "idle"
        self.detail = "尚未启动眼控，手机控制关闭"
        self.mode = "off"
        self.until = self.last_heartbeat = 0.0
        self.events_sent = 0
        self.failed = False
        self.closing = False
        self.trace = (self.directory / "session_events.jsonl").open("a", encoding="utf-8")
        self.loop_thread = threading.Thread(target=self._tick_loop, daemon=True)
        self.loop_thread.start()

    def record(self, event, **values):
        self.trace.write(json.dumps(dict(monotonic=time.monotonic(), event=event, **values)) + "\n")
        self.trace.flush()

    def disarm(self, reason):
        self.gate.disarm()
        was_active = self.mode != "off"
        self.mode = "off"
        self.detail = reason
        if was_active:
            try:
                self.receiver_state = self.receiver.command("STOP")
            except (OSError, ReceiverError):
                self.record("stop_unacknowledged", receiver_timeout_ms=600)
            self.record("disarmed", reason=reason)

    def begin_calibration(self):
        with self.lock:
            if self.worker is not None and self.worker.poll() is None:
                raise ValueError("已有眼控会话，请先结束它")
            if self.failed:
                raise ValueError("采样进程出现异常，请结束本次服务后重新检查")
            if self.worker is not None:
                self.worker.stdin.close()
                self.worker.stdout.close()
                self.worker_log.close()
            self.disarm("开始新的方向短校准，输出关闭")
            self.gate.clear()
            self.native_ready = self.trained = self.point_pending = False
            self.next_point = 0
            self.phase = "starting"
            capture = self.directory / ("capture_" + secrets.token_hex(8))
            capture.mkdir(mode=0o700)
            self.worker_log = (capture / "native.log").open("wb")
            # Same audited native direction mode and dimensions as the existing eye guide.
            # No OEM calibration/model computation or display/PL startup is requested.
            self.worker = subprocess.Popen([str(self.native), str(capture), "220", "160", "--relative-selection"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.worker_log, start_new_session=True)
            self.reader_thread = threading.Thread(target=self._read_native, args=(self.worker,), daemon=True)
            self.reader_thread.start()
            self.record("calibration_started", native_sha256=NATIVE_SHA)

    def collect_point(self):
        with self.lock:
            if not self.native_ready or self.point_pending or self.next_point >= 3:
                raise ValueError("采样尚未就绪，或上一点尚未结束")
            x, y = POINTS[self.next_point]
            self.worker.stdin.write(("point %d %.2f %.2f\n" % (self.next_point, x, y)).encode())
            self.worker.stdin.flush()
            self.point_pending = True
            self.detail = "请注视提示点，采样约 6 秒"

    def compute_direction(self):
        with self.lock:
            if self.next_point != 3 or self.point_pending or not self.native_ready or self.trained:
                raise ValueError("请先依次完成中、左、右三个点")
            self.worker.stdin.write(b"compute\n")
            self.worker.stdin.flush()
            self.phase = "computing"

    def _read_native(self, worker):
        try:
            while True:
                line = worker.stdout.readline(65537)
                if not line:
                    break
                if len(line) > 65536:
                    raise ValueError("Oversize native sample event")
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("Native event must be an object")
                with self.lock:
                    if self.worker is not worker or self.closing:
                        break
                    kind = event.get("kind")
                    if kind == "ready":
                        self.native_ready = True
                        self.phase = "calibration"
                        self.detail = "依次采集中、左、右三个点，每点 6 秒"
                    elif kind == "point":
                        if event.get("accepted") is not True or event.get("point") != self.next_point:
                            raise ValueError("Direction sample point rejected")
                        self.point_pending = False
                        self.next_point += 1
                        self.detail = "本点采样完成"
                    elif kind == "direction_ready":
                        if event.get("trained") is not True:
                            raise ValueError("Direction fit did not succeed")
                        self.trained = True
                        self.phase = "tracking"
                        self.detail = "短校准完成，先看中央约 0.6 秒；控制仍关闭"
                    elif kind == "horizontal_gaze" and self.trained:
                        action = self.gate.update(event, time.monotonic())
                        if self.mode != "off" and not self.gate.armed:
                            self.disarm("眼位无效或样本过期，已撤销控制；需手动重新开启")
                        if action and self.mode != "off":
                            self.receiver_state = self.receiver.command(action, self.gate.last_source)
                            self.events_sent += 1
                            self.record("eye_action", action=action, mode=self.mode,
                                        source_monotonic_ns=event["monotonic_ns"],
                                        result=self.receiver_state["result"])
                    elif kind == "error":
                        raise ValueError("Native eye sampler reported an error")
        except (ValueError, OSError, ReceiverError) as error:
            with self.lock:
                self.failed = True
                self.phase = "error"
                self.disarm("眼控会话异常，输出已关闭")
                self.record("eye_error", error_type=type(error).__name__)
        finally:
            with self.lock:
                if self.worker is worker and not self.closing:
                    self.native_ready = self.trained = False
                    self.gate.clear()
                    self.disarm("眼控采样已结束，输出关闭")
                    if self.phase != "error":
                        self.phase = "ended"

    def arm(self, mode, checked):
        with self.lock:
            if mode not in {"virtual", "hid"} or self.failed or not self.trained:
                raise ValueError("请先完成方向短校准")
            if mode == "hid" and checked is not True:
                raise ValueError("请确认手机抖音在前台、指针已位于视频中央")
            if self.mode != "off":
                raise ValueError("请先关闭已有控制")
            self.gate.arm(time.monotonic())
            try:
                self.receiver_state = self.receiver.command("ARM_HID" if mode == "hid" else "ARM_VIRTUAL")
            except (OSError, ReceiverError):
                self.gate.disarm()
                raise
            self.mode = mode
            self.until = time.monotonic() + 29
            self.last_heartbeat = time.monotonic()
            self.detail = "左侧停留：上一条；右侧停留：下一条；每次后必须回中央"
            self.record("armed", mode=mode, lease_seconds=29)

    def _tick_loop(self):
        while not self.closing:
            with self.lock:
                now = time.monotonic()
                if self.mode != "off":
                    if not self.gate.fresh(now) or now >= self.until:
                        self.disarm("断流或许可到期，控制已关闭；需手动重新开启")
                    elif now - self.last_heartbeat >= .15:
                        try:
                            self.receiver_state = self.receiver.command("HEARTBEAT", self.gate.last_source)
                            self.last_heartbeat = time.monotonic()
                        except (OSError, ReceiverError):
                            self.disarm("无线或蓝牙状态异常，控制已关闭")
            time.sleep(.02)

    def status(self):
        with self.lock:
            return dict(phase=self.phase, detail=self.detail, next_point=self.next_point,
                native_ready=self.native_ready, point_pending=self.point_pending, trained=self.trained,
                eye_fresh=self.gate.fresh(time.monotonic()), eye_region=self.gate.region,
                center_ready=self.gate.center_ready, dwell_progress=self.gate.progress,
                wait_center=self.gate.wait_center, output_mode=self.mode, events_sent=self.events_sent,
                lease_seconds=max(0, round(self.until - time.monotonic())) if self.mode != "off" else 0,
                receiver={key: self.receiver_state.get(key) for key in
                    ("product", "network_mode", "ble_ready", "virtual_commands", "hid_commands", "busy")},
                eye_control_acceptance="pending human calibration and test", pc_runtime_bridge=False,
                pl_configured=False, formal_apps_modified=False)

    def close(self):
        with self.lock:
            self.closing = True
            self.disarm("服务退出，控制关闭")
            worker = self.worker
        self.loop_thread.join(timeout=2)
        if worker is not None:
            if worker.poll() is None:
                os.killpg(worker.pid, signal.SIGTERM)
                try:
                    worker.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    self.record("native_cleanup_timeout")
                    os.killpg(worker.pid, signal.SIGKILL)
                    worker.wait(timeout=2)
            worker.stdin.close()
            if self.reader_thread is not None:
                self.reader_thread.join(timeout=2)
            worker.stdout.close()
        if self.worker_log is not None:
            self.worker_log.close()
        self.receiver.close()
        self.trace.close()


def main():
    import fcntl
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    if not 30 <= args.seconds <= 1800:
        raise ValueError("Session must be finite, at most 30 minutes")
    os.umask(0o077)
    root = Path(__file__).resolve().parent
    lock = (root / "phone_session.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    run = root / ("session_" + time.strftime("%Y%m%d_%H%M%S"))
    run.mkdir(mode=0o700)
    session = PhoneSession(load_config(args.config), args.native, run)
    token = secrets.token_hex(32)
    stopping = False

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(1)

        def log_message(self, *_):
            pass

        def reply(self, code, body, content_type="application/json"):
            data = json.dumps(body, ensure_ascii=False).encode() if content_type == "application/json" else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                self.reply(200, (root / "phone_control.html").read_text(encoding="utf-8").replace("__TOKEN__", token), "text/html")
            elif self.path == "/api/status":
                self.reply(200, session.status())
            else:
                self.reply(404, {"error": "not_found"})

        def do_POST(self):
            self.connection.settimeout(1)
            if (self.headers.get("X-Phone-Session") != token
                    or self.headers.get("Origin") not in (None, "http://192.168.50.1:9117")):
                self.reply(403, {"error": "explicit_local_session_required"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 2 <= length <= 256:
                    raise ValueError("Invalid request size")
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict) or set(value) - {"action", "mode", "phone_ready"}:
                    raise ValueError("Invalid explicit control request")
                action = value.get("action")
                if self.path != "/api/control":
                    raise ValueError("Unknown control path")
                if action == "calibrate":
                    session.begin_calibration()
                elif action == "point":
                    session.collect_point()
                elif action == "compute":
                    session.compute_direction()
                elif action == "arm":
                    session.arm(value.get("mode"), value.get("phone_ready"))
                elif action == "stop":
                    with session.lock:
                        session.disarm("用户关闭控制")
                else:
                    raise ValueError("Unsupported explicit action")
                self.reply(200, session.status())
            except (ValueError, OSError, ReceiverError) as error:
                self.reply(409, {"error": str(error) if isinstance(error, ValueError) else "连接异常，控制未开启"})

    def stop_signal(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    deadline = time.monotonic() + args.seconds
    server = None
    try:
        server = ThreadingHTTPServer(("192.168.50.1", 9117), Handler)
        server.timeout = .2
        server.socket.settimeout(1)
        print(json.dumps(dict(event="phone_eye_session_ready", url="http://192.168.50.1:9117/",
                              seconds=args.seconds, output_mode="off", usb_opened=False, pl_configured=False)), flush=True)
        while not stopping and time.monotonic() < deadline:
            server.handle_request()
    finally:
        if server is not None:
            server.server_close()
        session.close()
        lock.close()


if __name__ == "__main__":
    main()

"""Single-client HTTP window receiver for the existing PYNQ GuardianLoop PL."""

import argparse
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np

from guardianloop_pynq import CHANNELS, WINDOW_SAMPLES, GuardianLoopPynq


WINDOW_BYTES = WINDOW_SAMPLES * CHANNELS * 2


def _atomic_json(path, payload):
    if not path:
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                    separators=(",", ":")), encoding="utf-8")
    temporary.replace(destination)


def publish_dashboard(result, samples, source, status_path, telemetry_path):
    """Expose an HTTP replay/LSL window to the separate dashboard service."""
    state = str(result.get("state", "INVALID")).lower()
    prediction = bool(result.get("valid")) and state in ("normal", "mild", "severe")
    offline = source == "seedvig_replay"
    status = {
        "source": source,
        "offline": offline,
        "valid": prediction,
        "level": state if prediction else "unknown",
        "state": "prediction" if prediction else (
            "calibrating" if state == "calibrating" else "invalid"),
        "seq": int(result.get("window", 0)),
        "score": result.get("smoothed_perclos"),
        "raw_ratio": result.get("perclos"),
        "window_seconds": 8,
        "window_hop_seconds": 8,
        "calibration_current": int(result.get("calibration_current", 0)),
        "calibration_total": int(result.get("calibration_total", 15)),
        "algorithm_version": "guardianloop-pynq-pl-v1",
        "updated_at": int(time.time()),
        "signal_quality": "通过" if result.get("valid") else "未通过",
        "reason": result.get("reason"),
        "reference_perclos": result.get("reference_perclos"),
        "packets_seen": 0,
        "dropped_packets": 0,
        "sequence_gaps": 0,
        "malformed_bytes": 0,
        "clipped_rows": 0,
    }
    # Dashboard rendering needs only the latest five seconds at 125 Hz.
    microvolts = samples.astype(np.float64) / 100.0
    telemetry = {
        "source": source,
        "real": False if offline else source == "cyton_usb",
        "offline": offline,
        "updated_at": time.time(),
        "sample_rate_hz": 125,
        "channels": CHANNELS,
        "samples": np.round(microvolts[-1250::2], 3).tolist(),
        "packets_seen": 0,
        "dropped_packets": 0,
        "packet_loss_percent": 0.0,
        "sequence_gaps": 0,
        "malformed_bytes": 0,
        "clipped_rows": 0,
    }
    _atomic_json(status_path, status)
    _atomic_json(telemetry_path, telemetry)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="192.168.2.99")
    parser.add_argument("--port", type=int, default=9101)
    parser.add_argument("--status-file", default="/run/guardianloop/status.json")
    parser.add_argument("--telemetry-file", default="/run/guardianloop/telemetry.json")
    args = parser.parse_args()
    token = os.environ.get("GL_PYNQ_TOKEN", "")
    if len(token) < 16:
        raise SystemExit("Set GL_PYNQ_TOKEN to a private value of at least 16 characters")
    engine = GuardianLoopPynq()

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status, body):
            payload = json.dumps(body, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _authorized(self):
            return hmac.compare_digest(self.headers.get("X-GuardianLoop-Token", ""), token)

        def do_GET(self):
            if self.path != "/health":
                self._reply(404, {"error": "unknown_path"})
            elif not self._authorized():
                self._reply(401, {"error": "unauthorized"})
            else:
                self._reply(200, {"loaded": engine.overlay.is_loaded(),
                                  "windows": engine.window_index,
                                  "calibration_current": len(engine.baseline),
                                  "calibration_ready": engine.mean is not None})

        def do_POST(self):
            if self.path != "/window":
                self._reply(404, {"error": "unknown_path"})
                return
            if not self._authorized():
                self._reply(401, {"error": "unauthorized"})
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length != WINDOW_BYTES:
                self._reply(400, {"error": "window_must_be_32000_bytes"})
                return
            payload = self.rfile.read(length)
            if len(payload) != WINDOW_BYTES:
                self._reply(400, {"error": "partial_window"})
                return
            window = np.frombuffer(payload, dtype="<i2").reshape(WINDOW_SAMPLES, CHANNELS)
            transport_ok = self.headers.get("X-Transport-OK", "0") == "1"
            source = self.headers.get("X-GuardianLoop-Source", "http_window")
            if source not in ("http_window", "lsl", "seedvig_replay"):
                source = "http_window"
            try:
                result = engine.process_window(window, transport_ok=transport_ok)
            except Exception as exc:
                print(f"WINDOW_PROCESSING_ERROR: {exc}", flush=True)
                self._reply(500, {"valid": False, "state": "INVALID",
                                  "error": type(exc).__name__, "detail": str(exc)})
                return
            reference = self.headers.get("X-Reference-PERCLOS")
            if reference is not None:
                try:
                    result["reference_perclos"] = min(1.0, max(0.0, float(reference)))
                except ValueError:
                    pass
            publish_dashboard(result, window, source, args.status_file, args.telemetry_file)
            print(f"WINDOW_RESULT: {json.dumps(result, sort_keys=True)}", flush=True)
            self._reply(200, result)

    server = HTTPServer((args.bind, args.port), Handler)
    print(f"GUARDIANLOOP_PYNQ_READY: http://{args.bind}:{args.port} ", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

"""Read-only, metadata-only audit of the deployed Z15 three-task stack."""
import hashlib
import json
from pathlib import Path
import shlex

import requests

from run_soak_stage import ROOT, PROD, connect, command


OUT = ROOT / "eeg_apps_z15/output/integration_acceptance_20260927"
FILES = (
    "cyton_guardianloop.py", "guardianloop_web.py", "cyton_sqi.py",
    "cyton_covariance.py", "cyton_fatigue.py", "seed_shadow.py",
    "seed_quality_runtime.py", "seed_shadow_policy.py", "ssvep_shadow.py",
    "ssvep_stream.py", "ssvep_core.py", "gameemo_covariance_svm.npz",
    "cyton_fatigue_overlap4.json", "seed_shadow_weights.npz",
    "ssvep_causal_protocol.json", "ssvep_candidate_sos.npy",
    "guardianloop_pynq.bit", "guardianloop_pynq.hwh",
)
UNITS = ("guardianloop-cyton.service", "guardianloop-web.service",
         "guardianloop-ap.service", "guardianloop-dhcp.service")


def json_from_url(path):
    response = requests.get("http://192.168.2.99:9102" + path, timeout=6)
    response.raise_for_status()
    return response.json()


def model_metadata(sftp):
    with sftp.open(PROD + "/cyton_fatigue_overlap4.json") as handle:
        fatigue = json.load(handle)
    with sftp.open(PROD + "/ssvep_causal_protocol.json") as handle:
        ssvep = json.load(handle)
    return {
        "fatigue": {key: fatigue.get(key) for key in
                    ("channels", "calibration_windows", "sample_rate_hz", "window_seconds",
                     "source_dataset", "target", "thresholds") if key in fatigue},
        "ssvep": {key: ssvep.get(key) for key in
                  ("fixed_cap", "selected_cap_indices", "sample_rate_hz", "batch_samples",
                   "window_samples", "hop_samples", "warmup_samples", "frequencies_hz")
                  if key in ssvep},
    }


def summarize_http():
    status = json_from_url("/api/status")
    telemetry = json_from_url("/api/telemetry")
    seed = json_from_url("/api/seed-shadow")
    ssvep = json_from_url("/api/ssvep-shadow")
    recording = json_from_url("/api/recording")
    health = requests.get("http://192.168.2.99:9102/healthz", timeout=6)
    fatigue = status.get("fatigue") or {}
    system = status.get("system") or {}
    live_telemetry = telemetry.get("telemetry") or {}
    runtime = live_telemetry.get("runtime") or {}
    emotion = live_telemetry.get("emotion") or {}
    seed_live = seed.get("live") or {}
    ssvep_live = ssvep.get("live") or {}
    return {
        "health_http": health.status_code,
        "status": {"stale": status.get("stale"),
                   "fatigue": {key: fatigue.get(key) for key in
                               ("valid", "state", "reason", "level", "fatigue_model_channels")},
                   "system": {key: system.get(key) for key in
                              ("ap_active", "cyton_active", "web_active") if key in system}},
        "telemetry": {"stale": telemetry.get("stale"), "source": live_telemetry.get("source"),
                      "real": live_telemetry.get("real"),
                      "channel_map": live_telemetry.get("channel_map"),
                      "packets_seen": live_telemetry.get("packets_seen"),
                      "emotion": {key: emotion.get(key) for key in
                                  ("valid", "state", "model_channels", "usable_channels")},
                      "runtime": {key: runtime.get(key) for key in
                                  ("reader_queue_delay_ms", "input_age_at_snapshot_ms",
                                   "primary_stream_resets")}},
        "seed_live": {key: seed_live.get(key) for key in
                      ("state", "valid", "source", "reason", "policy_version")},
        "ssvep_live": {key: ssvep_live.get(key) for key in
                       ("state", "valid", "frequency_hz", "source", "control_enabled",
                        "reason", "policy_version")},
        "recording_state": (recording.get("recording") or {}).get("state"),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    client = connect()
    try:
        quoted = " ".join(shlex.quote(PROD + "/" + name) for name in FILES)
        lines = command(client, "sha256sum " + quoted).splitlines()
        hashes = {Path(path).name: digest for digest, path in
                  (line.split(maxsplit=1) for line in lines)}
        services = {}
        for unit in UNITS:
            raw = command(client, "systemctl show " + unit
                          + " -p ActiveState -p UnitFileState -p MainPID -p NRestarts -p FragmentPath")
            services[unit] = dict(row.split("=", 1) for row in raw.splitlines() if "=" in row)
        with client.open_sftp() as sftp:
            models = model_metadata(sftp)
        ap_address = command(client, "ip -br addr show wlan0").strip()
        # Keep only known, non-secret startup markers. Never export unit environment or AP credentials.
        journal = command(client, "journalctl -u guardianloop-cyton.service -n 200 --no-pager")
        allowed = ("FATIGUE_MODEL_READY", "FATIGUE_MODEL_DISABLED", "COVARIANCE_MODEL_READY",
                   "COVARIANCE_MODEL_DISABLED", "EMOTION_MODEL_READY", "EMOTION_MODEL_DISABLED",
                   "CYTON_EEG_CHANNELS_CONFIGURED", "CYTON_STREAM_STARTED", "SSVEP_SHADOW_DISABLED",
                   "SEED_SHADOW_DISABLED")
        markers = [row.strip() for row in journal.splitlines() if any(word in row for word in allowed)]
        audit = {"scope": "read_only_board_and_http_metadata; no raw EEG, credentials, reset or PL writes",
                 "production_path": PROD, "files_sha256": hashes,
                 "services": services, "models": models,
                 "wlan0_address": ap_address, "startup_markers": markers[-20:],
                 "http": summarize_http()}
        (OUT / "board_snapshot.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
        compact = {"services": services, "models": models, "wlan0_address": ap_address,
                   "startup_markers": markers[-8:], "http": audit["http"],
                   "hash_count": len(hashes)}
        print(json.dumps(compact, ensure_ascii=False, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()

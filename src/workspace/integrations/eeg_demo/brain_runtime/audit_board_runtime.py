"""Read-only audit of fixed-cap models, board services, and dashboard freshness.

An unavailable board is reported as unverified, never as a passing check. This
script does not start acquisition, alter service enablement, or load an overlay.
"""

import argparse
import hashlib
import json
import logging
import shlex
from pathlib import Path

import paramiko

from cyton_covariance import CovarianceSVM
from cyton_fatigue import CHANNELS as FATIGUE_CHANNELS, FourChannelFatigue


HERE = Path(__file__).resolve().parent
FATIGUE = (HERE.parent / "viformer_z15" / "output" /
           "cyton_montage_fatigue_v2" / "cyton_fatigue_overlap4.json")
COVARIANCE = HERE / "gameemo_covariance_svm.npz"
REMOTE = "/home/xilinx/jupyter_notebooks/guardianloop_pynq"
CHANNEL_MAP = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
MODEL_FILES = {"fatigue": (FATIGUE, "cyton_fatigue_overlap4.json"),
               "emotion": (COVARIANCE, "gameemo_covariance_svm.npz")}
CODE_FILES = ("cyton_guardianloop.py", "cyton_sqi.py", "cyton_fatigue.py",
              "cyton_covariance.py", "guardianloop_web.py")
SERVICES = ("guardianloop-ap", "guardianloop-dhcp", "guardianloop-web",
            "guardianloop-cyton")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def local_contract():
    fatigue = FourChannelFatigue(FATIGUE)
    emotion = CovarianceSVM(COVARIANCE)
    if tuple(fatigue.model["channels"]) != FATIGUE_CHANNELS:
        raise ValueError("Fatigue model channel mismatch")
    if tuple(emotion.metadata["channels"]) != ("F3", "F4", "T7", "T8", "O1", "O2"):
        raise ValueError("Emotion model channel mismatch")
    return {"physical_channels": CHANNEL_MAP,
            "fatigue_channels": FATIGUE_CHANNELS,
            "emotion_channels": tuple(emotion.metadata["channels"]),
            "model_sha256": {kind: sha256(path) for kind, (path, _) in MODEL_FILES.items()},
            "code_sha256": {filename: sha256(HERE / filename) for filename in CODE_FILES}}


def remote_script():
    lines = ["set -u", "printf 'kernel='; uname -r"]
    for service in SERVICES:
        name = shlex.quote(service + ".service")
        lines.append(f"printf '{service}.active='; systemctl is-active {name} || true")
        lines.append(f"printf '{service}.enabled='; systemctl is-enabled {name} || true")
    lines.extend(("printf 'wlan0='; iw dev wlan0 info 2>/dev/null | awk '$1==\"type\" {print $2}'",
                  "printf 'receiver='; test -e /dev/ttyUSB0 && echo present || echo absent",
                  "printf 'channel_map_override=%s\\n' \"$(sed -n 's/^GL_CHANNEL_MAP=//p' /etc/default/guardianloop-cyton 2>/dev/null | tail -1)\"",
                  "printf 'covariance_model_override=%s\\n' \"$(sed -n 's/^GL_COVARIANCE_MODEL=//p' /etc/default/guardianloop-cyton 2>/dev/null | tail -1)\""))
    for kind, (_, filename) in MODEL_FILES.items():
        path = shlex.quote(f"{REMOTE}/{filename}")
        lines.append(f"printf '{kind}.sha256='; test -f {path} && sha256sum {path} | awk '{{print $1}}' || echo missing")
    for filename in CODE_FILES:
        path = shlex.quote(f"{REMOTE}/{filename}")
        lines.append(f"printf 'code.{filename}.sha256='; test -f {path} && sha256sum {path} | awk '{{print $1}}' || echo missing")
    lines.append("printf 'api='; curl -fsS --max-time 5 http://127.0.0.1:9102/api/status || true")
    return "\n".join(lines)


def board_snapshot(host, user, password):
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, username=user, password=password, timeout=5,
                       banner_timeout=5, auth_timeout=5)
        _, stdout, stderr = client.exec_command(remote_script(), timeout=20)
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")
        if stdout.channel.recv_exit_status():
            raise RuntimeError(error or output)
    finally:
        client.close()
    values = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    values["api"] = json.loads(values["api"]) if values.get("api") else None
    return values


def assess(local, remote):
    issues = []
    for kind in MODEL_FILES:
        if remote.get(f"{kind}.sha256") != local["model_sha256"][kind]:
            issues.append(f"{kind} model missing or SHA-256 differs from audited local candidate")
    for filename, expected in local["code_sha256"].items():
        if remote.get(f"code.{filename}.sha256") != expected:
            issues.append(f"{filename} missing or SHA-256 differs from audited local code")
    for service in SERVICES[:3]:
        if remote.get(f"{service}.active") != "active":
            issues.append(f"{service} is not active")
    if remote.get("wlan0") != "AP":
        issues.append("wlan0 is not in AP mode")
    override = remote.get("channel_map_override", "").strip("\"'")
    if override and tuple(part.strip().upper() for part in override.split(",")) != CHANNEL_MAP:
        issues.append("effective GL_CHANNEL_MAP override differs from fixed physical montage")
    covariance_override = remote.get("covariance_model_override", "").strip("\"'")
    if covariance_override and covariance_override != f"{REMOTE}/gameemo_covariance_svm.npz":
        issues.append("GL_COVARIANCE_MODEL points away from audited six-channel SVM")
    api = remote.get("api")
    if api is None:
        issues.append("dashboard status API unavailable")
    return {"model_and_dashboard_ready": not issues, "issues": issues,
            "acquisition_active": remote.get("guardianloop-cyton.active") == "active",
            "data_fresh": bool(api is not None and not api.get("stale", True))}


def main():
    logging.getLogger("paramiko.transport").setLevel(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.2.99")
    parser.add_argument("--user", default="xilinx")
    parser.add_argument("--password", default="xilinx")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {"local": local_contract(), "remote": None, "assessment": None}
    if not args.local_only:
        try:
            report["remote"] = board_snapshot(args.host, args.user, args.password)
            report["assessment"] = assess(report["local"], report["remote"])
        except (OSError, paramiko.SSHException, RuntimeError, ValueError,
                KeyError, json.JSONDecodeError) as exc:
            report["remote_error"] = f"{type(exc).__name__}: {exc}"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not args.local_only and report["assessment"] is None:
        raise SystemExit(2)
    if report["assessment"] is not None and not report["assessment"]["model_and_dashboard_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Isolated Z15 replay: real recorded parity and labeled synthetic fault recovery.

No production service writes, no USB access, no PL loading, no accuracy claims.
"""
import hashlib
import json
from pathlib import Path
import shlex
import time

from run_soak_stage import ROOT, PROD, connect

OUT = ROOT / "eeg_apps_z15/output/mixed_cyton_replay_20260927"
PYTHON = "/usr/local/share/pynq-venv/bin/python3"
EXPECTED_SSVEP = "b618f558b96a6c2d9dc3e783e8df54c342ec83d1323360c36f815f788ef08247"


def remote(client, command, timeout=135):
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    text = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
    status = stdout.channel.recv_exit_status()
    if status:
        raise RuntimeError(f"exit={status}: {text[-1600:]}")
    return text


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_case(client, stage, label, args):
    output = stage + "/" + label + "-result"
    prefix = stage + ("/baseline" if label == "recorded-baseline" else "/candidate")
    call = ("timeout -s TERM -k 5 115 env PYTHONPATH="
            + shlex.quote(prefix + ":" + stage + ":" + PROD)
            + " OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr " + PYTHON
            + " " + stage + "/soak_service_replay.py"
            + " --input " + stage + "/input.npz --output " + output + " " + args)
    remote(client, call)
    with client.open_sftp() as sftp:
        for filename in ("report.json", "producer.json", "monitor.jsonl", "primary_results.json",
                         "status.json", "ssvep.json", "offline-replay.log"):
            sftp.get(output + "/" + filename, str(OUT / (label + "-" + filename)))
    report = json.loads((OUT / (label + "-report.json")).read_text())
    return {"label": label, "report": report,
            "producer": json.loads((OUT / (label + "-producer.json")).read_text())}


def main():
    if OUT.exists():
        raise RuntimeError("Output already exists; preserve earlier evidence")
    OUT.mkdir(parents=True)
    client = connect()
    stage = "/home/xilinx/jupyter_notebooks/mixed_cyton_replay_" + time.strftime("%Y%m%d-%H%M%S")
    try:
        with client.open_sftp() as sftp:
            sftp.mkdir(stage)
            sftp.mkdir(stage + "/baseline")
            sftp.mkdir(stage + "/candidate")
            sftp.get(PROD + "/ssvep_shadow.py", str(OUT / "production_ssvep.py"))
            if sha(OUT / "production_ssvep.py") != EXPECTED_SSVEP:
                raise RuntimeError("Production SSVEP module changed; inspect before comparison")
            baseline = ROOT / "eeg_apps_z15/output/ssvep_rail_coalesce_20260927/production_before.py"
            sftp.put(str(baseline), stage + "/baseline/ssvep_shadow.py")
            sftp.put(str(OUT / "production_ssvep.py"), stage + "/candidate/ssvep_shadow.py")
            sftp.put(str(ROOT / "pynq_guardianloop/soak_service_replay.py"),
                     stage + "/soak_service_replay.py")
            sftp.put(str(ROOT / "eeg_apps_z15/output/board_pipeline_profile_20260926/input.npz"),
                     stage + "/input.npz")
        manifest = {"stage": stage, "baseline_ssvep_sha256": sha(baseline),
                    "candidate_ssvep_sha256": EXPECTED_SSVEP,
                    "input_sha256": sha(ROOT / "eeg_apps_z15/output/board_pipeline_profile_20260926/input.npz"),
                    "production_before": remote(client, "systemctl show guardianloop-cyton -p MainPID -p NRestarts -p ActiveState"),
                    "cases": []}
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        cases = (
            ("recorded-baseline", "--seconds 25 --input-kind recorded"),
            ("recorded-candidate", "--seconds 25 --input-kind recorded"),
            ("mixed-candidate", "--seconds 70 --input-kind synthetic --pause-at 3750 --pause-seconds 1.0 --rail-from 7500 --rail-to 8750"),
        )
        for label, args in cases:
            print("RUN", label, flush=True)
            result = run_case(client, stage, label, args)
            manifest["cases"].append(result)
            (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            print("DONE", label, "consumed", result["report"]["packets_consumed"],
                  "p95_ms", result["report"]["packet_input_age_p95_ms"], flush=True)
        manifest["production_after"] = remote(client, "systemctl show guardianloop-cyton -p MainPID -p NRestarts -p ActiveState")
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    finally:
        client.close()


if __name__ == "__main__":
    main()

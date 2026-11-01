"""Stage and compare isolated paced Cyton replays with synthetic ADC rails.

Production services/files are read only. The replay forbids USB and PL access.
"""
import hashlib
import json
from pathlib import Path
import shlex
import time

from run_soak_stage import ROOT, PROD, connect

OUT = ROOT / "eeg_apps_z15/output/ssvep_rail_coalesce_20260927"
PYTHON = "/usr/local/share/pynq-venv/bin/python3"


def call(client, command, timeout=120):
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode(errors="replace")
    error = stderr.read().decode(errors="replace")
    status = stdout.channel.recv_exit_status()
    if status:
        raise RuntimeError(f"exit={status}\n{output[-2500:]}\n{error[-2500:]}")
    return output + error


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "manifest.json"
    if manifest.exists():
        raise RuntimeError("Existing comparison manifest; inspect before rerunning")
    client = connect()
    stage = "/home/xilinx/jupyter_notebooks/ssvep_rail_compare_" + time.strftime("%Y%m%d-%H%M%S")
    try:
        with client.open_sftp() as sftp:
            sftp.mkdir(stage)
            sftp.mkdir(stage + "/original")
            sftp.mkdir(stage + "/candidate")
            prod_copy = OUT / "production_before.py"
            sftp.get(PROD + "/ssvep_shadow.py", str(prod_copy))
            expected = OUT.parent / "ssvep_cache_20260927/original/ssvep_shadow.py"
            if digest(prod_copy) != digest(expected):
                raise RuntimeError("Production SSVEP module differs from audited original")
            candidate = OUT / "ssvep_shadow.py"
            for label, path in (("original", prod_copy), ("candidate", candidate)):
                sftp.put(str(path), stage + "/" + label + "/ssvep_shadow.py")
            sftp.put(str(ROOT / "pynq_guardianloop/soak_service_replay.py"),
                     stage + "/soak_service_replay.py")
            sftp.put(str(ROOT / "eeg_apps_z15/output/board_pipeline_profile_20260926/input.npz"),
                     stage + "/input.npz")
        before = call(client, "systemctl show guardianloop-cyton -p MainPID -p NRestarts -p ActiveState")
        bitstreams = call(client, "sha256sum " + PROD + "/guardianloop_pynq.bit " + PROD + "/guardianloop_pynq.hwh")
        metadata = {"stage": stage, "production_sha256": digest(prod_copy),
                    "candidate_sha256": digest(candidate), "services_before": before,
                    "bitstream_hashes": bitstreams, "seconds_each": 30,
                    "synthetic_rail": True, "source": "isolated_paced_replay_only"}
        manifest.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        for label in ("original", "candidate"):
            remote_output = stage + "/" + label + "-run"
            command = ("env PYTHONPATH=" + shlex.quote(stage + "/" + label + ":" + stage + ":" + PROD)
                       + " OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr " + PYTHON
                       + " " + stage + "/soak_service_replay.py"
                       + " --input " + stage + "/input.npz"
                       + " --output " + remote_output + " --seconds 30 --force-rail")
            try:
                call(client, command, timeout=110)
                with client.open_sftp() as sftp:
                    sftp.get(remote_output + "/report.json", str(OUT / (label + "-report.json")))
                    sftp.get(remote_output + "/producer.json", str(OUT / (label + "-producer.json")))
                    sftp.get(remote_output + "/offline-replay.log", str(OUT / (label + "-replay.log")))
                print(label, (OUT / (label + "-report.json")).read_text(), flush=True)
            except Exception as exc:
                (OUT / (label + "-error.txt")).write_text(str(exc), encoding="utf-8")
                print(label, "FAILED", str(exc), flush=True)
        metadata["services_after"] = call(client, "systemctl show guardianloop-cyton -p MainPID -p NRestarts -p ActiveState")
        manifest.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        client.close()


if __name__ == "__main__":
    main()

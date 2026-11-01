"""Isolated SSVEP A/B replay on Z15; never changes the live service or PL.

Run --stage, inspect event parity, then --paired. The frozen acceptance rule
is documented in output/ssvep_quality_gate_20260930/PLAN.md.
"""

import argparse
import hashlib
import json
import shlex
import statistics
import time
from pathlib import Path

import numpy as np

from run_accepted_bench_load import PROD, PYTHON, ROOT, connect, remote


OUT = ROOT / "eeg_apps_z15/output/ssvep_quality_gate_20260930"
INPUT = ROOT / "eeg_apps_z15/output/pl_integrated_candidate_20260929/recorded_input.npz"
CANDIDATE = {
    "ssvep_shadow.py": ROOT / "pynq_guardianloop/ssvep_shadow.py",
    "ssvep_stream.py": ROOT / "eeg_apps_z15/ssvep_stream.py",
    "ssvep_core.py": ROOT / "eeg_apps_z15/ssvep_core.py",
    "cyton_sqi.py": ROOT / "pynq_guardianloop/cyton_sqi.py",
}
PRODUCTION_AUDITED = {
    "ssvep_shadow.py": "b618f558b96a6c2d9dc3e783e8df54c342ec83d1323360c36f815f788ef08247",
    "ssvep_stream.py": "b2dea502cb1e54f543aad139af1504b9c4c12a5365f1e9b4e53f601176097613",
    "ssvep_core.py": "9594807f16c5f10198809ac02dec7efad6857ee4657b6ab33d83835ad4edb1e6",
    "cyton_sqi.py": "9e99682ae8b284cf4cdabb251997952b6cd9facda25486ff15133e06007e6d12",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def module_hashes(client):
    with client.open_sftp() as sftp:
        return {
            name: hashlib.sha256(sftp.open(PROD + "/" + name, "rb").read()).hexdigest()
            for name in CANDIDATE
        }


def copy_result(client, source, name):
    with client.open_sftp() as sftp:
        sftp.get(source, str(OUT / name))


def save_manifest(manifest):
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def assert_event_parity(left, right):
    if len(left) != len(right):
        raise AssertionError(f"event count differs: {len(left)} vs {len(right)}")
    largest_score_difference = 0.0
    for index, (old, new) in enumerate(zip(left, right)):
        for key in ("state", "reason", "window_start_index", "window_end_index_exclusive",
                    "frequency_hz", "target_index", "quality", "control_enabled",
                    "sequence_gaps"):
            if old[key] != new[key]:
                raise AssertionError(f"event {index} differs in {key}")
        if (old["scores"] is None) != (new["scores"] is None):
            raise AssertionError(f"event {index} score presence differs")
        if old["scores"] is not None:
            np.testing.assert_allclose(old["scores"], new["scores"], atol=1e-9, rtol=1e-7)
            np.testing.assert_allclose(old["margin"], new["margin"], atol=1e-9, rtol=1e-7)
            largest_score_difference = max(
                largest_score_difference,
                float(np.max(np.abs(np.asarray(old["scores"]) - new["scores"]))),
            )
    return {"passed": True, "events": len(left),
            "max_abs_score_difference": largest_score_difference,
            "score_atol": 1e-9, "score_rtol": 1e-7}


def stage():
    if (OUT / "manifest.json").exists():
        raise RuntimeError("Previous stage exists; preserve its evidence")
    with np.load(INPUT) as data:
        if data["recorded"].shape[0] < 20_000 or data["recorded"].shape[1] != 8:
            raise ValueError("Input needs at least 20,000 eight-channel samples")
    client = connect()
    try:
        before = module_hashes(client)
        if before != PRODUCTION_AUDITED:
            raise RuntimeError("Production SSVEP modules changed; re-audit before replay")
        production_services = remote(
            client, "systemctl show guardianloop-cyton guardianloop-web "
                    "-p MainPID -p NRestarts -p ActiveState"
        )
        stage_path = "/home/xilinx/jupyter_notebooks/ssvep_quality_gate_" + time.strftime("%Y%m%d_%H%M%S")
        candidate_path = stage_path + "/candidate"
        with client.open_sftp() as sftp:
            sftp.mkdir(stage_path)
            sftp.mkdir(candidate_path)
            for name, path in CANDIDATE.items():
                sftp.put(str(path), candidate_path + "/" + name)
            for name, path in {
                "input.npz": INPUT,
                "soak_service_replay.py": ROOT / "pynq_guardianloop/soak_service_replay.py",
                "replay_stage_trace.py": ROOT / "pynq_guardianloop/replay_stage_trace.py",
                "replay_ssvep_bench_events.py": ROOT / "eeg_apps_z15/replay_ssvep_bench_events.py",
            }.items():
                sftp.put(str(path), stage_path + "/" + name)
        manifest = {
            "stage": stage_path, "candidate": candidate_path,
            "input_sha256": digest(INPUT),
            "candidate_sha256": {name: digest(path) for name, path in CANDIDATE.items()},
            "production_sha256_before": before,
            "production_services_before": production_services,
            "scope": "Isolated replay. No live service, Cyton USB, PL, or model modification.",
        }
        save_manifest(manifest)
        for label, module_path in (("baseline", PROD), ("candidate", candidate_path + ":" + PROD)):
            print("EVENT_REPLAY_START", label, flush=True)
            output = stage_path + "/events_" + label
            command = (
                "cd " + shlex.quote(stage_path) + " && timeout -s TERM -k 5 95 env "
                "PYTHONPATH=" + shlex.quote(module_path) + " OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr "
                + PYTHON + " replay_ssvep_bench_events.py --input input.npz --output "
                + shlex.quote(output)
            )
            print(remote(client, command, timeout=105)[-1200:], flush=True)
            copy_result(client, output + "/events.json", label + "_events.json")
        parity = assert_event_parity(
            json.loads((OUT / "baseline_events.json").read_text(encoding="utf-8")),
            json.loads((OUT / "candidate_events.json").read_text(encoding="utf-8")),
        )
        (OUT / "event_parity.json").write_text(json.dumps(parity, indent=2) + "\n", encoding="utf-8")
        manifest["production_sha256_after_events"] = module_hashes(client)
        manifest["production_services_after_events"] = remote(
            client, "systemctl show guardianloop-cyton guardianloop-web "
                    "-p MainPID -p NRestarts -p ActiveState"
        )
        save_manifest(manifest)
        if manifest["production_sha256_after_events"] != before:
            raise RuntimeError("Production module hashes changed during event replay")
        print("EVENT_PARITY", json.dumps(parity), flush=True)
    finally:
        client.close()


def run_paired():
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    parity = json.loads((OUT / "event_parity.json").read_text(encoding="utf-8"))
    if not parity["passed"]:
        raise RuntimeError("Event parity gate failed")
    stage_path, candidate_path = manifest["stage"], manifest["candidate"]
    cases = (("a1", PROD), ("c1", candidate_path + ":" + PROD),
             ("c2", candidate_path + ":" + PROD), ("a2", PROD))
    if any((OUT / f"{label}_report.json").exists() for label, _ in cases):
        raise RuntimeError("Prior paired report exists; preserve it")
    client = connect()
    try:
        client.get_transport().set_keepalive(15)
        before = module_hashes(client)
        if before != manifest["production_sha256_before"]:
            raise RuntimeError("Production hashes changed after stage")
        manifest["production_services_before_paired"] = remote(
            client, "systemctl show guardianloop-cyton guardianloop-web "
                    "-p MainPID -p NRestarts -p ActiveState"
        )
        save_manifest(manifest)
        for label, module_path in cases:
            print("PAIRED_START", label, flush=True)
            output = stage_path + "/paced_" + label
            prefix = "/dev/shm/ssvep_gate_" + time.strftime("%Y%m%d_%H%M%S") + "_" + label
            command = (
                "cd " + shlex.quote(stage_path) + " && timeout -s TERM -k 5 120 env "
                "PYTHONPATH=" + shlex.quote(module_path) + " OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr "
                + PYTHON + " soak_service_replay.py --input input.npz --input-kind recorded "
                + "--filter-backend arm --seconds 80 --trace-stages --output " + shlex.quote(output)
                + " --volatile-primary-dir " + shlex.quote(prefix + "_primary")
                + " --volatile-shadow-dir " + shlex.quote(prefix + "_shadow")
            )
            print(remote(client, command, timeout=135)[-1000:], flush=True)
            for filename in ("report.json", "stages.json", "primary_results.json", "ssvep.json",
                             "monitor.jsonl", "offline-replay.log"):
                try:
                    copy_result(client, output + "/" + filename, label + "_" + filename)
                except FileNotFoundError:
                    if filename in ("report.json", "stages.json", "primary_results.json"):
                        raise
            report = json.loads((OUT / f"{label}_report.json").read_text(encoding="utf-8"))
            print("PAIRED_DONE", label, json.dumps({key: report[key] for key in (
                "packets_consumed", "packet_input_age_p95_ms", "packet_input_age_max_ms",
                "parent_cpu_seconds", "children_cpu_seconds", "error")}), flush=True)
        manifest["production_sha256_after_paired"] = module_hashes(client)
        manifest["production_services_after_paired"] = remote(
            client, "systemctl show guardianloop-cyton guardianloop-web "
                    "-p MainPID -p NRestarts -p ActiveState"
        )
        save_manifest(manifest)
        if manifest["production_sha256_after_paired"] != before:
            raise RuntimeError("Production module hashes changed during paired replay")
    finally:
        client.close()


def audit():
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    parity = json.loads((OUT / "event_parity.json").read_text(encoding="utf-8"))
    if "production_sha256_after_paired" not in manifest:
        raise RuntimeError("All paired runs must finish before audit")
    runs = {}
    primary = {}
    for label in ("a1", "c1", "c2", "a2"):
        report = json.loads((OUT / f"{label}_report.json").read_text(encoding="utf-8"))
        stages = json.loads((OUT / f"{label}_stages.json").read_text(encoding="utf-8"))["stages"]
        primary[label] = json.loads((OUT / f"{label}_primary_results.json").read_text(encoding="utf-8"))
        runs[label] = {
            "packets_consumed": report["packets_consumed"],
            "packets_expected": report["packets_expected"],
            "input_age_p95_ms": report["packet_input_age_p95_ms"],
            "input_age_max_ms": report["packet_input_age_max_ms"],
            "total_cpu_s": report["parent_cpu_seconds"] + report["children_cpu_seconds"],
            "packet_compute_p99_ms": report["packet_compute_p99_ms"],
            "wall_s": report["wall_seconds"],
            "ssvep_packet_stage_wall_s": stages["ssvep_packet"]["wall_s"],
            "ssvep_quality_stage_wall_s": stages["ssvep_quality"]["wall_s"],
            "ssvep_decision_stage_wall_s": stages["ssvep_decision"]["wall_s"],
            "ssvep_stream_push_stage_wall_s": stages["ssvep_stream_push"]["wall_s"],
            "monitor_errors": report["monitor_errors"],
            "error": report["error"],
            "remaining_children": report["remaining_children"],
            "clean_run": report["packets_consumed"] == report["packets_expected"] == 20_000
                         and not report["monitor_errors"] and not report["error"]
                         and not report["remaining_children"],
            "primary_results_exact_vs_a1": primary[label] == primary["a1"],
        }
    baseline_cpu = statistics.median(runs[name]["total_cpu_s"] for name in ("a1", "a2"))
    baseline_age = statistics.median(runs[name]["input_age_p95_ms"] for name in ("a1", "a2"))
    for name in ("c1", "c2"):
        row = runs[name]
        row["cpu_reduction_vs_arm_median"] = (baseline_cpu - row["total_cpu_s"]) / baseline_cpu
        row["input_age_reduction_vs_arm_median"] = (baseline_age - row["input_age_p95_ms"]) / baseline_age
        row["candidate_gate_pass"] = (
            row["clean_run"] and row["primary_results_exact_vs_a1"]
            and row["cpu_reduction_vs_arm_median"] >= 0.10
            and row["input_age_p95_ms"] < 500
            and row["input_age_max_ms"] < 3000
            and row["input_age_p95_ms"] <= baseline_age
        )
    hashes_stable = (
        manifest["production_sha256_before"] == manifest["production_sha256_after_events"]
        == manifest["production_sha256_after_paired"]
    )
    result = {
        "input_sha256": manifest["input_sha256"],
        "production_sha256": manifest["production_sha256_before"],
        "candidate_sha256": manifest["candidate_sha256"],
        "event_parity": parity,
        "runs": runs,
        "arm_two_run_median_cpu_s": baseline_cpu,
        "arm_two_run_median_input_age_p95_ms": baseline_age,
        "production_hashes_stable": hashes_stable,
        "candidate_isolated_gate_pass": parity["passed"] and hashes_stable
            and all(runs[name]["candidate_gate_pass"] for name in ("c1", "c2"))
            and all(runs[name]["clean_run"] for name in ("a1", "a2")),
        "deployed_to_production": False,
        "pl_acceleration_tested": False,
    }
    (OUT / "audit.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("stage", "paired", "audit"))
    args = parser.parse_args()
    {"stage": stage, "paired": run_paired, "audit": audit}[args.phase]()


if __name__ == "__main__":
    main()

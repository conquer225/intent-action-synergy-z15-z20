"""Post-deployment replay gate for the guarded ARM SSVEP rollout."""

import json
import shlex
import statistics

from deploy_ssvep_quality_candidate import BITSTREAMS, LEDGER, check_files, check_web, rollback
from run_accepted_bench_load import PROD, PYTHON, connect, remote
from run_ssvep_quality_gate import OUT


def copy_result(client, remote_path, local_path):
    with client.open_sftp() as sftp:
        sftp.get(remote_path, str(local_path))


def run():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    if ledger["phase"] != "installed_pending_replay":
        raise RuntimeError("Deployment is not awaiting replay")
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    stage = manifest["stage"]
    client = connect()
    try:
        client.get_transport().set_keepalive(15)
        with client.open_sftp() as sftp:
            if check_files(sftp, ledger["candidate"]) != ledger["candidate"]:
                raise RuntimeError("Installed module hashes changed")
        for number in (1, 2):
            label = f"post_deploy_{number}"
            if (OUT / f"{label}_report.json").exists():
                raise RuntimeError(f"Prior {label} report exists; preserve it")
            print("POST_DEPLOY_REPLAY_START", label, flush=True)
            output = stage + "/" + label
            primary = "/dev/shm/ssvep_deploy_gate_" + str(number) + "_primary"
            shadow = "/dev/shm/ssvep_deploy_gate_" + str(number) + "_shadow"
            command = (
                "cd " + shlex.quote(stage) + " && timeout -s TERM -k 5 120 env "
                "PYTHONPATH=" + shlex.quote(PROD) + " OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr "
                + PYTHON + " soak_service_replay.py --input input.npz --input-kind recorded "
                "--filter-backend arm --seconds 80 --trace-stages --output " + shlex.quote(output)
                + " --volatile-primary-dir " + shlex.quote(primary)
                + " --volatile-shadow-dir " + shlex.quote(shadow)
            )
            print(remote(client, command, timeout=135)[-1000:], flush=True)
            for filename in ("report.json", "stages.json", "primary_results.json", "monitor.jsonl"):
                copy_result(client, output + "/" + filename, OUT / f"{label}_{filename}")
            report = json.loads((OUT / f"{label}_report.json").read_text(encoding="utf-8"))
            print("POST_DEPLOY_REPLAY_DONE", label, json.dumps({key: report[key] for key in (
                "packets_consumed", "packet_input_age_p95_ms", "packet_input_age_max_ms",
                "parent_cpu_seconds", "children_cpu_seconds", "error")}), flush=True)
        with client.open_sftp() as sftp:
            after = check_files(sftp, ledger["candidate"])
            bit_after = check_files(sftp, BITSTREAMS)
        ledger["post_replay_module_hashes"] = after
        ledger["post_replay_bitstream_hashes"] = bit_after
        ledger["post_replay_web"] = check_web(client)
        ledger["post_replay_service_status"] = remote(
            client, "systemctl show guardianloop-cyton guardianloop-web "
                    "-p MainPID -p NRestarts -p ActiveState -p SubState"
        )
        LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        client.close()
        rollback()
        raise
    finally:
        client.close()


def audit():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    paired = json.loads((OUT / "audit.json").read_text(encoding="utf-8"))
    expected_primary = json.loads((OUT / "c1_primary_results.json").read_text(encoding="utf-8"))
    baseline_cpu = statistics.median(paired["runs"][name]["total_cpu_s"] for name in ("a1", "a2"))
    output = {"baseline_median_cpu_s": baseline_cpu, "runs": {}}
    for number in (1, 2):
        label = f"post_deploy_{number}"
        report = json.loads((OUT / f"{label}_report.json").read_text(encoding="utf-8"))
        results = json.loads((OUT / f"{label}_primary_results.json").read_text(encoding="utf-8"))
        total_cpu = report["parent_cpu_seconds"] + report["children_cpu_seconds"]
        row = {
            "packets_consumed": report["packets_consumed"],
            "input_age_p95_ms": report["packet_input_age_p95_ms"],
            "input_age_max_ms": report["packet_input_age_max_ms"],
            "total_cpu_s": total_cpu,
            "cpu_reduction_vs_old_production_median": (baseline_cpu - total_cpu) / baseline_cpu,
            "primary_results_exact": results == expected_primary,
            "monitor_errors": report["monitor_errors"],
            "remaining_children": report["remaining_children"],
            "error": report["error"],
        }
        row["pass"] = (
            row["packets_consumed"] == report["packets_expected"] == 20_000
            and row["input_age_p95_ms"] < 500
            and row["input_age_max_ms"] < 3000
            and row["cpu_reduction_vs_old_production_median"] >= 0.10
            and row["primary_results_exact"]
            and not row["monitor_errors"] and not row["remaining_children"] and not row["error"]
        )
        output["runs"][label] = row
    output["module_hashes_stable"] = ledger.get("post_replay_module_hashes") == ledger["candidate"]
    output["bitstream_hashes_stable"] = ledger.get("post_replay_bitstream_hashes") == BITSTREAMS
    output["web_safe"] = (
        ledger.get("post_replay_web", {}).get("live_source") == "live"
        and ledger.get("post_replay_web", {}).get("control_enabled") is False
    )
    output["promotion_pass"] = (
        all(row["pass"] for row in output["runs"].values())
        and output["module_hashes_stable"] and output["bitstream_hashes_stable"]
        and output["web_safe"]
    )
    (OUT / "post_deploy_audit.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    ledger["phase"] = "deployed_verified" if output["promotion_pass"] else "post_replay_failed"
    LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False), flush=True)
    if not output["promotion_pass"]:
        rollback()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("run", "audit"))
    args = parser.parse_args()
    {"run": run, "audit": audit}[args.phase]()


if __name__ == "__main__":
    main()

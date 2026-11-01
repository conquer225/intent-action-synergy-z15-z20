"""Opt-in stage timing for the already-staged accepted bench replay."""
import json
from pathlib import Path
import shlex

from run_accepted_bench_load import OUT, PROD, ROOT, PYTHON, SECONDS, connect, remote


def main():
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "profile" in manifest:
        raise RuntimeError("Stage profile already recorded; preserve it")
    stage = manifest["stage"]
    client = connect()
    try:
        manifest["profile_production_before"] = remote(client, "systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState")
        with client.open_sftp() as sftp:
            sftp.put(str(ROOT / "pynq_guardianloop/replay_stage_trace.py"), stage + "/replay_stage_trace.py")
        print("STAGE_PROFILE_START", flush=True)
        command = ("cd " + shlex.quote(stage) + " && timeout -s TERM -k 5 205 env "
                   "PYTHONPATH=" + shlex.quote(PROD) + " OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr "
                   + PYTHON + " soak_service_replay.py --input input.npz --input-kind recorded "
                   "--output profiled-result --seconds " + str(SECONDS) + " --trace-stages")
        print(remote(client, command), flush=True)
        with client.open_sftp() as sftp:
            for name in ("report.json", "producer.json", "monitor.jsonl", "primary_results.json",
                         "status.json", "shadow.json", "ssvep.json", "offline-replay.log",
                         "stages.json", "web_stages.json", "telemetry_stages.json", "slow_packets.json"):
                try:
                    sftp.get(stage + "/profiled-result/" + name, str(OUT / ("profile-" + name)))
                except FileNotFoundError:
                    pass
        manifest["profile_production_after"] = remote(client, "systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState")
        manifest["profile"] = {"trace_file": str(OUT / "profile-stages.json"),
                               "input_kind": "non-wear bench", "stage_instrumentation": True}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        report = json.loads((OUT / "profile-report.json").read_text(encoding="utf-8"))
        stages = json.loads((OUT / "profile-stages.json").read_text(encoding="utf-8"))["stages"]
        print("PROFILE_REPORT", json.dumps({key: report.get(key) for key in
              ("packets_consumed", "packets_expected", "packet_input_age_p95_ms",
               "packet_input_age_max_ms", "parent_cpu_seconds", "children_cpu_seconds", "error")}))
        print("PROFILE_STAGES", json.dumps({key: {k: round(v, 3) if isinstance(v, float) else v for k, v in value.items()}
              for key, value in stages.items()}), flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    main()

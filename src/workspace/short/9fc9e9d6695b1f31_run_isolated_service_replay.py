"""Run one paced candidate replay on Z15; never access live Cyton or public status."""

import argparse
import json
from pathlib import Path
import re
import shlex
import sys


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from run_soak_stage import connect, command  # noqa: E402
from deploy_ssvep_rail_coalesce import sudo  # noqa: E402


REMOTE = "/home/xilinx/guardianloop_pl_service_candidate_20260929"
PROD = "/home/xilinx/jupyter_notebooks/guardianloop_pynq"
LOCAL_OUTPUT = APP / "output" / "pl_integrated_candidate_20260929"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backend", choices=("arm", "pl"))
    parser.add_argument("--seconds", type=int, default=80)
    parser.add_argument("--label", default="", help="Unique suffix for an isolated retry")
    parser.add_argument("--trace-stages", action="store_true")
    parser.add_argument("--rank2-ssvep", action="store_true",
                        help="Use isolated two-channel analytic CCA solver")
    parser.add_argument("--tmpfs-shadow", action="store_true",
                        help="Write isolated SSVEP/SEED status to a unique tmpfs directory")
    parser.add_argument("--tmpfs-primary", action="store_true",
                        help="Write isolated primary status to tmpfs like the live /run path")
    parser.add_argument("--async-seed", action="store_true",
                        help="Bound SEED shadow in a replay-only worker process")
    parser.add_argument("--audit-seed", action="store_true",
                        help="Capture isolated SEED transitions and freshness")
    parser.add_argument("--input-kind", choices=("recorded", "synthetic"), default="recorded")
    parser.add_argument("--pause-at", type=int, help="Inject one isolated packet-feed pause")
    parser.add_argument("--pause-seconds", type=float, default=0.0)
    parser.add_argument("--reader-fault-after", type=int,
                        help="Inject a terminal serial I/O fault after this many packets")
    args = parser.parse_args()
    if not 8 <= args.seconds <= 180:
        raise ValueError("Replay must be between 8 and 180 seconds")
    if args.label and not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", args.label):
        raise ValueError("Replay label must be a short file-safe identifier")
    if (args.pause_at is None) != (args.pause_seconds == 0.0):
        raise ValueError("Pause position and duration must be given together")
    if args.pause_at is not None and not (0 < args.pause_at < args.seconds * 250
                                          and args.pause_at % 10 == 0
                                          and 0 < args.pause_seconds <= 5):
        raise ValueError("Invalid pause position or duration")
    if args.reader_fault_after is not None and not 0 < args.reader_fault_after < args.seconds * 250:
        raise ValueError("Reader fault must occur inside the replay")
    name = f"{args.backend}_replay_{args.seconds}s" + (f"_{args.label}" if args.label else "")
    destination = REMOTE + "/" + name
    client = connect()
    try:
        if command(client, "systemctl is-active guardianloop-cyton.service || true").strip() != "inactive":
            raise RuntimeError("Formal Cyton service must be inactive")
        command(client, "test ! -e " + shlex.quote(destination))
        if args.backend == "pl":
            command(client, "test -e /proc/device-tree/amba/dma-owner@40410000 && "
                            "test -c /dev/guardianloop_dma_keeper")
            if not command(client, "lsmod | grep '^gldma_owner '").strip():
                raise RuntimeError("Candidate DMA owner module missing")
        program = (
            f"env PYTHONPATH={PROD} XILINX_XRT=/usr "
            + ("GUARDIANLOOP_EXPERIMENTAL_RANK2_CCA=1 " if args.rank2_ssvep else "") +
            "/usr/local/share/pynq-venv/bin/python3 "
            f"{REMOTE}/soak_service_replay.py --input {REMOTE}/input.npz "
            f"--output {destination} --seconds {args.seconds} "
            f"--filter-backend {args.backend} --input-kind {args.input_kind}"
        )
        if args.pause_at is not None:
            program += f" --pause-at {args.pause_at} --pause-seconds {args.pause_seconds}"
        if args.reader_fault_after is not None:
            program += f" --reader-fault-after {args.reader_fault_after}"
        if args.trace_stages:
            program += " --trace-stages"
        if args.tmpfs_shadow:
            program += f" --volatile-shadow-dir /dev/shm/{name}_shadow"
        if args.tmpfs_primary:
            program += f" --volatile-primary-dir /dev/shm/{name}_primary"
        if args.async_seed:
            program += " --async-seed-candidate"
        if args.audit_seed:
            program += " --audit-seed-candidate"
        invocation = "sudo -S -p '' " + program if args.backend == "pl" else program
        stdin, stdout, stderr = client.exec_command(invocation, timeout=args.seconds + 90)
        if args.backend == "pl":
            stdin.write("xilinx\n")
            stdin.flush()
        text = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
        result = stdout.channel.recv_exit_status()
        print(text[-3000:])
        if result and args.reader_fault_after is None:
            raise RuntimeError(f"Replay failed with exit code {result}; inspect isolated logs")
        if not result and args.reader_fault_after is not None:
            raise RuntimeError("Injected reader fault unexpectedly exited successfully")
        if args.backend == "pl":
            sudo(client, "chown -R xilinx:xilinx " + shlex.quote(destination))
        with client.open_sftp() as sftp:
            local_report = LOCAL_OUTPUT / f"{name}_report.json"
            sftp.get(destination + "/report.json", str(local_report))
            if args.audit_seed:
                audit_dir = (f"/dev/shm/{name}_shadow" if args.tmpfs_shadow else destination)
                sftp.get(audit_dir + "/shadow.events.jsonl",
                         str(LOCAL_OUTPUT / f"{name}_seed_events.jsonl"))
                sftp.get(audit_dir + "/shadow.json",
                         str(LOCAL_OUTPUT / f"{name}_seed_final.json"))
            if args.trace_stages:
                sftp.get(destination + "/stages.json",
                         str(LOCAL_OUTPUT / f"{name}_stages.json"))
        report = json.loads(local_report.read_text(encoding="utf-8"))
        if args.reader_fault_after is not None:
            if "CytonReaderError" not in str(report.get("error")):
                raise RuntimeError("Replay did not report the expected reader fault")
            if report.get("packets_consumed") != args.reader_fault_after:
                raise RuntimeError("Replay fault occurred at the wrong packet count")
        print(f"REPLAY_REPORT={local_report}")
        print("SUMMARY " + json.dumps({
            key: report[key] for key in (
                "filter_backend", "requested_seconds", "packets_consumed",
                "packets_expected", "packet_input_age_p95_ms",
                "packet_input_age_max_ms", "packet_compute_p99_ms", "error",
                "monitor_errors", "remaining_children",
            )
        }))
    finally:
        client.close()


if __name__ == "__main__":
    main()

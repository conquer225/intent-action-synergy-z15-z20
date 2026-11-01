"""Read-only, short Z15 queue/SSVEP I/O diagnostic; no EEG samples exported."""
import json
import sys
import time

from run_soak_stage import connect, command


def remote_json(sftp, path):
    try:
        with sftp.open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def proc_io(client, pid):
    try:
        output = command(client, f"cat /proc/{pid}/io")
    except RuntimeError:
        return {}
    return {key.rstrip(":"): int(value) for key, value in
            (line.split() for line in output.splitlines())}


def snapshot(client, sftp):
    status = command(client, "systemctl show guardianloop-cyton -p MainPID -p NRestarts -p ActiveState")
    fields = dict(line.split("=", 1) for line in status.splitlines() if "=" in line)
    pid = int(fields.get("MainPID", "0"))
    ssvep = remote_json(sftp, "/tmp/guardianloop-ssvep-shadow.json")
    telemetry = remote_json(sftp, "/run/guardianloop/telemetry.json")
    runtime = telemetry.get("runtime") or {}
    return {
        "pid": pid, "restarts": fields.get("NRestarts"), "active": fields.get("ActiveState"),
        "ssvep_packets": ssvep.get("packets_seen"), "ssvep_state": ssvep.get("state"),
        "ssvep_reason": ssvep.get("reason"), "ssvep_age": ssvep.get("input_age_seconds"),
        "main_packets": telemetry.get("packets_seen"),
        "queue_delay_ms": runtime.get("reader_queue_delay_ms"),
        "input_age_ms": runtime.get("input_age_at_snapshot_ms"),
        "io": proc_io(client, pid) if pid else {},
    }


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    client = connect()
    try:
        with client.open_sftp() as sftp:
            before = snapshot(client, sftp)
            time.sleep(seconds)
            after = snapshot(client, sftp)
        print(json.dumps({"seconds": seconds, "before": before, "after": after},
                         ensure_ascii=False, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()

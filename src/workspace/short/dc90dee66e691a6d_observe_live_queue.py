"""Read-only sustained Z15 queue observation (metadata only, no EEG export)."""
import json
from pathlib import Path
import statistics
import sys
import time

from diagnose_live_queue import snapshot
from run_soak_stage import connect


def main():
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    client = connect()
    try:
        with client.open_sftp() as sftp:
            rows = []
            deadline = time.monotonic() + seconds
            while True:
                row = snapshot(client, sftp)
                row.pop("io", None)
                rows.append(row)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(5, remaining))
        delays = [r["queue_delay_ms"] for r in rows if r["queue_delay_ms"] is not None]
        result = {"seconds": seconds, "samples": len(rows), "pid_first": rows[0]["pid"],
                  "pid_last": rows[-1]["pid"], "restart_first": rows[0]["restarts"],
                  "restart_last": rows[-1]["restarts"],
                  "packet_delta": (rows[-1]["main_packets"] - rows[0]["main_packets"]
                                   if rows[0]["main_packets"] is not None and rows[-1]["main_packets"] is not None else None),
                  "queue_delay_min_ms": min(delays) if delays else None,
                  "queue_delay_median_ms": statistics.median(delays) if delays else None,
                  "queue_delay_max_ms": max(delays) if delays else None,
                  "rows": rows}
        body = json.dumps(result, ensure_ascii=False, indent=2)
        if output:
            output.write_text(body, encoding="utf-8")
        print(body)
    finally:
        client.close()


if __name__ == "__main__":
    main()

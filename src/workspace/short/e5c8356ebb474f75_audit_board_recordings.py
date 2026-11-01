"""Read-only inventory of board trial recordings; avoid exporting EEG or private labels."""
import json
from datetime import datetime, timezone

from run_soak_stage import connect, command, PROD


def main():
    client = connect()
    try:
        print("SERVICES", command(client, "systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState").strip())
        print("RECORDING_PATHS", command(client, "find /home/xilinx/jupyter_notebooks -maxdepth 5 -type d -name recordings -print").strip())
        print("EEG_FILE_PATHS", command(client, "find /home/xilinx/jupyter_notebooks -maxdepth 6 -type f \\( -name 'samples_i32le.bin' -o -name 'OpenBCI-RAW-*.txt' -o -name '*2026-09-25*' \\) -print").strip())
        print("CYTON_JOURNAL_RANGE", command(client, "journalctl -u guardianloop-cyton --since '2026-09-25 00:00:00' --until '2026-09-26 00:00:00' --no-pager -o short-iso 2>/dev/null | wc -l").strip())
        with client.open_sftp() as sftp:
            root = PROD + "/recordings"
            try:
                names = sftp.listdir(root)
            except OSError as exc:
                print("NO_RECORDING_ROOT", type(exc).__name__)
                return
            print("TRIAL_COUNT", len(names))
            for name in sorted(names):
                folder = root + "/" + name
                try:
                    with sftp.open(folder + "/metadata.json") as handle:
                        meta = json.load(handle)
                    files = {entry.filename: entry.st_size for entry in sftp.listdir_attr(folder)}
                except (OSError, ValueError, TypeError) as exc:
                    print("TRIAL_UNREADABLE", name, type(exc).__name__)
                    continue
                epoch = meta.get("browser_started_at_ms")
                started = datetime.fromtimestamp(epoch / 1000, timezone.utc).isoformat() if isinstance(epoch, (float, int)) else None
                print(json.dumps({
                    "trial": name,
                    "browser_started_utc": started,
                    "board_started": meta.get("started_at"),
                    "channel_map": meta.get("channel_map"),
                    "sample_rate": meta.get("sample_rate"),
                    "samples": meta.get("samples"),
                    "duration_s": meta.get("duration_s"),
                    "state": meta.get("state"),
                    "files_bytes": files,
                }, ensure_ascii=False))
    finally:
        client.close()


if __name__ == "__main__":
    main()

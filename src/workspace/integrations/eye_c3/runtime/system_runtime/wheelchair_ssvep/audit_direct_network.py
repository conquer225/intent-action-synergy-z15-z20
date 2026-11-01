"""Read-only board/receiver audit; does not change network, services or firmware."""
import argparse
import json
from pathlib import Path
import sys
import subprocess
import time
from paramiko import SSHException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eeg_apps_z15"))
from run_soak_stage import connect
from reload_formal_wireless import netsh, wait_board
from bench_serial_check import Bench


def audit(host):
    result = {"host": host, "mutation_performed": False}
    client = None
    try:
        client = connect(host=host)
        command = ("uname -a; ip -br addr; iw dev; "
                   "cat /proc/sys/kernel/random/boot_id; "
                   "systemctl show guardianloop-cyton.service guardianloop-web.service "
                   "-p MainPID -p NRestarts -p ActiveState; "
                   "systemctl list-unit-files --no-pager 'guardianloop*'; "
                   "cat /proc/device-tree/model")
        _, stdout, stderr = client.exec_command(command, timeout=10)
        result["board_readonly"] = stdout.read().decode("utf-8", errors="replace")
        result["stderr"] = stderr.read().decode("utf-8", errors="replace")
        result["exit_code"] = stdout.channel.recv_exit_status()
    except (OSError, TimeoutError, SSHException) as error:
        result["board_error"] = type(error).__name__
    finally:
        if client is not None:
            client.close()
    bench = Bench("COM16")
    try:
        bench.serial.open()
        result["receiver"] = bench.request("STATUS")
    finally:
        bench.serial.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.2.99")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--via-saved-hotspot", action="store_true")
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Use a new report path")
    if args.via_saved_hotspot and args.host != "192.168.50.1":
        parser.error("Saved hotspot access requires 192.168.50.1")
    result = None
    try:
        if args.via_saved_hotspot:
            interfaces = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], timeout=5).decode(errors="replace")
            if "JLU.WIFI" not in interfaces:
                raise RuntimeError("Expected original PC Wi-Fi JLU.WIFI; do not change an unknown connection")
            netsh("GuardianLoop-Z15")
            wait_board()
        result = audit(args.host)
    finally:
        if args.via_saved_hotspot:
            netsh("JLU.WIFI")
            for _ in range(20):
                interfaces = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], timeout=5).decode(errors="replace")
                if "JLU.WIFI" in interfaces:
                    break
                time.sleep(0.5)
            print("PC_WIFI_RESTORED " + str("JLU.WIFI" in interfaces), flush=True)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

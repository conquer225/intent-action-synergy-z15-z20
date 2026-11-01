"""Stage a finite, GPIO-disabled virtual test on Z15; restore the PC Wi-Fi afterwards."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REMOTE = "/home/xilinx/wheelchair_virtual_20261006"
MAC = "30:ed:a0:a2:e4:24"
sys.path.insert(0, str(ROOT.parent / "eeg_apps_z15"))
from reload_formal_wireless import netsh, wait_board
from run_soak_stage import connect
from run_ssvep_backlog_replay import checked
from bench_serial_check import Bench


def receiver_address(client):
    neighbors = checked(client, "ip neigh show dev wlan0")
    matches = re.findall(
        r"^(192\.168\.50\.(?:[2-9]|[1-9]\d|1\d\d|2[0-4]\d|25[0-4]))"
        r" lladdr " + re.escape(MAC) + r" (?:REACHABLE|STALE|DELAY|PROBE)\s*$",
        neighbors, re.M | re.I)
    if len(set(matches)) != 1:
        raise ValueError("Expected a unique wlan0 neighbor for the verified ESP32 MAC")
    return matches[-1]


def verify_protected(client, before):
    services = checked(client, "systemctl show guardianloop-cyton.service guardianloop-web.service "
                       "-p MainPID -p NRestarts -p ActiveState")
    actual = {}
    with client.open_sftp() as sftp:
        for path in before["protected_before"]:
            with sftp.open(path) as stream:
                actual[path] = hashlib.sha256(stream.read()).hexdigest()
    if services != before["services_before"] or actual != before["protected_before"]:
        raise ValueError("Protected production files or service identity changed; do not start/continue")
    return {"services_unchanged": True, "protected_files_unchanged": True,
            "protected_file_count": len(actual), "services": services}


def run(output):
    before = json.loads((ROOT / "output/station_profile_prepare_20261006.json").read_text())
    profile = (ROOT / "firmware/guardianloop_wheelchair/config_private.h").read_text()
    key_match = re.search(r'^#define WC_AUTH_TOKEN "([0-9a-f]{64})"$', profile, re.M)
    if key_match is None:
        raise ValueError("Private receiver key unavailable")
    client = None
    bench = Bench("COM16")
    result = {"status": "not_started", "physical_motor_output_tested": False,
              "remote_test_directory": REMOTE, "original_services_modified": False}
    try:
        bench.serial.open()
        initial = bench.request("STATUS")
        if not initial["link_ready"] or initial["state"]["armed"]:
            raise ValueError("Station receiver must be connected and disarmed")
        netsh("GuardianLoop-Z15")
        wait_board()
        client = connect(host="192.168.50.1")
        result["before"] = verify_protected(client, before)
        address = receiver_address(client)
        result["receiver_address"] = address
        with client.open_sftp() as sftp:
            try:
                sftp.stat(REMOTE)
            except FileNotFoundError:
                sftp.mkdir(REMOTE, mode=0o700)
            else:
                raise FileExistsError("Existing remote test directory; inspect instead of overwriting")
            for name in ("bench_network_bridge.py", "dry_run_bridge.py", "mapping.json",
                         "network_bench_acceptance.py", "test_network_bridge.py"):
                sftp.put(str(ROOT / name), REMOTE + "/" + name)
            config = json.dumps({"receiver_url": "http://" + address, "auth_key": key_match.group(1)})
            with sftp.open(REMOTE + "/receiver_private.json", "wx") as stream:
                stream.write(config)
            sftp.chmod(REMOTE + "/receiver_private.json", 0o600)
        result["arm_sender_unit_tests"] = checked(client, "cd " + REMOTE + " && python3 -m unittest -v test_network_bridge")
        command = ("cd " + REMOTE + " && python3 -u network_bench_acceptance.py "
                   "--config receiver_private.json --report network_report.json")
        _, stdout, stderr = client.exec_command(command, timeout=50)
        for line in stdout:
            row = json.loads(line)
            if row.get("event") == "local_arm_required":
                state = bench.request("STATUS")["state"]
                if state["armed"] or state["requested_direction"] != "stop":
                    raise ValueError("Local virtual receiver is not ready")
                bench.arm()
            print(line.strip(), flush=True)
        error = stderr.read().decode()
        code = stdout.channel.recv_exit_status()
        if code:
            raise RuntimeError("Finite remote virtual test failed: " + error)
        with client.open_sftp() as sftp:
            with sftp.open(REMOTE + "/network_report.json") as stream:
                result["network_test"] = json.loads(stream.read())
        result["live_source_observer"] = checked(client, "cd " + REMOTE + " && python3 -u bench_network_bridge.py "
            "--config receiver_private.json --source-url http://127.0.0.1:9102/api/ssvep-free --seconds 5")
        result["after"] = verify_protected(client, before)
        result["final_receiver"] = bench.request("STATUS")
        if result["final_receiver"]["state"]["armed"] or result["final_receiver"]["state"]["requested_direction"] != "stop":
            raise AssertionError("Final receiver must be disarmed and STOP")
        result["status"] = "passed"
        return result
    finally:
        if bench.serial.is_open:
            if bench.verified:
                bench.serial.write(b"STOP\n")
            bench.serial.close()
        if client is not None:
            client.close()
        netsh("JLU.WIFI")
        for _ in range(20):
            interfaces = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], timeout=5).decode(errors="replace")
            if "JLU.WIFI" in interfaces:
                break
            time.sleep(.5)
        result["pc_wifi_restored"] = "JLU.WIFI" in interfaces
        with output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
        print("PC_WIFI_RESTORED " + str(result["pc_wifi_restored"]), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Use a new report path")
    result = run(args.report)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in {"live_source_observer", "arm_sender_unit_tests", "network_test"}}, indent=2))


if __name__ == "__main__":
    main()

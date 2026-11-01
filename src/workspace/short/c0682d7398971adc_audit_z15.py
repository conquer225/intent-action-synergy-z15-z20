"""Read-only Z15 eye/network audit; no USB, PL, service or receiver operations."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "eeg_apps_z15"))
from reload_formal_wireless import netsh, wait_board
from run_soak_stage import connect


@contextmanager
def board_connection():
    interfaces = subprocess.check_output(
        ["netsh", "wlan", "show", "interfaces"], timeout=5).decode(errors="replace")
    match = re.search(r"^\s*Profile\s*:\s*(.+?)\s*$", interfaces, re.M)
    if not match or match.group(1) not in {"JLU.WIFI", "GuardianLoop-Z15"}:
        raise RuntimeError("Unknown PC Wi-Fi profile; refusing to switch it")
    original_profile = match.group(1)
    client = None
    try:
        if original_profile != "GuardianLoop-Z15":
            netsh("GuardianLoop-Z15")
        wait_board()
        client = connect(host="192.168.50.1")
        client.get_transport().set_keepalive(5)
        yield client
    finally:
        if client is not None:
            client.close()
        if original_profile != "GuardianLoop-Z15":
            netsh(original_profile)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                restored = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], timeout=5).decode(errors="replace")
                if re.search(r"^\s*Profile\s*:\s*" + re.escape(original_profile) + r"\s*$", restored, re.M):
                    print("PC_WIFI_PROFILE_RESTORED", flush=True)
                    break
                time.sleep(.5)
            else:
                print("PC_WIFI_RESTORE_REQUESTED_NOT_CONFIRMED", flush=True)


def execute(client, command):
    _, stdout, stderr = client.exec_command(command, timeout=20)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if stdout.channel.recv_exit_status():
        raise RuntimeError("Read-only Z15 command failed: " + err[:400])
    return out


def audit(client):
    base = "/home/xilinx/jupyter_notebooks/guardianloop_pynq"
    result = {"host": "192.168.50.1", "mutation_performed": False}
    result["system"] = execute(client, "uname -a; ip -br addr; iw dev; "
        "cat /proc/sys/kernel/random/boot_id; "
        "systemctl show guardianloop-cyton.service guardianloop-web.service "
        "-p MainPID -p NRestarts -p ActiveState; "
        "systemctl list-units --state=running --no-legend 'brain-eye*' 'tobii*' 'phone-eye*'; "
        "pgrep -af 'is4-calibration|hdmi_guide|tobii_z15|coexist_session' || true")
    result["protected_sha256"] = {}
    with client.open_sftp() as sftp:
        path = base + "/release_manifest.json"
        with sftp.open(path) as stream:
            manifest_bytes = stream.read()
        manifest = json.loads(manifest_bytes)
        result["brain_release"] = {key: manifest.get(key) for key in
                                   ("release", "version", "created_at")}
        paths = [path]
        for name in manifest["files"]:
            if "/" in name or name in {".", ".."}:
                raise ValueError("Unexpected release path")
            paths.append(base + "/" + name)
        for directory in ("/home/xilinx/tobii_z15", "/home/xilinx/brain_eye_coexist_20261005/eye"):
            names = sftp.listdir(directory)
            result[directory + "_files"] = names
            for name in ("src/selection.py", "src/calibration_worker.py", "src/hdmi_guide.py",
                         "src/calibration.c", "is4-calibration", "overlay/eye_wifi.bit", "overlay/eye_wifi.hwh"):
                target = directory + "/" + name
                try:
                    sftp.stat(target)
                except FileNotFoundError:
                    continue
                paths.append(target)
        for path in paths:
            with sftp.open(path) as stream:
                digest = hashlib.sha256()
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    digest.update(chunk)
                result["protected_sha256"][path] = digest.hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Use a new report path")
    with board_connection() as client:
        result = audit(client)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in result.items()
                      if key != "protected_sha256"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

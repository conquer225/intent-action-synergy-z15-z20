"""Read Z15 AP credentials privately and patch only the ignored ESP bench profile."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "eeg_apps_z15"))
from reload_formal_wireless import netsh, wait_board
from run_soak_stage import connect
from run_ssvep_backlog_replay import checked


def prepare():
    profile = ROOT / "firmware/guardianloop_wheelchair/config_private.h"
    original = profile.read_text(encoding="utf-8")
    if not re.search(r"^#define WC_ENABLE_MOTOR_GPIO 0$", original, re.M):
        raise ValueError("Profile must disable motor GPIO")
    if not re.search(r'^#define WC_STA_SSID ""$', original, re.M):
        raise ValueError("Expected unchanged AP bench profile")
    client = None
    try:
        netsh("GuardianLoop-Z15")
        wait_board()
        client = connect(host="192.168.50.1")
        pid = checked(client, "systemctl show guardianloop-ap.service -p MainPID --value").strip()
        if not pid.isdecimal() or int(pid) <= 1:
            raise ValueError("Active Z15 AP service has no process to inspect")
        args = checked(client, "cat /proc/" + pid + "/cmdline", sudo=True).split("\0")
        configs = [arg for arg in args if re.fullmatch(r"/etc/[A-Za-z0-9_/.-]+\.conf", arg)]
        if len(configs) != 1:
            raise ValueError("Cannot resolve a single active hostapd configuration")
        if configs[0] != "/etc/guardianloop/ap.conf":
            raise ValueError("Unexpected active Z15 AP configuration path")
        text = checked(client, "cat " + shlex.quote(configs[0]), sudo=True)
        values = {}
        for line in text.splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if key in {"ssid", "psk", "mode", "proto", "key_mgmt"}:
                    if key in values:
                        raise ValueError("Ambiguous hotspot settings")
                    values[key] = value
        ssid = json.loads(values.get("ssid", '""'))
        if (ssid != "GuardianLoop-Z15" or values.get("mode") != "2"
                or values.get("key_mgmt") != "WPA-PSK" or values.get("proto") != "RSN"):
            raise ValueError("Unexpected active wpa_supplicant AP identity/security")
        password = json.loads(values.get("psk", '""'))
        if not 12 <= len(password) <= 63:
            return {"status": "hotspot_password_not_compatible_with_existing_bench_policy",
                    "ssid": ssid, "passphrase_length": len(password),
                    "profile_changed": False, "z15_network_changed": False}
        services = checked(client, "systemctl show guardianloop-cyton.service guardianloop-web.service "
                           "-p MainPID -p NRestarts -p ActiveState")
        manifest_path = "/home/xilinx/jupyter_notebooks/guardianloop_pynq/release_manifest.json"
        with client.open_sftp() as sftp:
            with sftp.open(manifest_path) as stream:
                manifest_bytes = stream.read()
            manifest = json.loads(manifest_bytes)
            protected = {manifest_path: hashlib.sha256(manifest_bytes).hexdigest()}
            for name in manifest["files"]:
                if "/" in name or name in {".", ".."}:
                    raise ValueError("Unexpected release file path")
                path = "/home/xilinx/jupyter_notebooks/guardianloop_pynq/" + name
                with sftp.open(path) as stream:
                    protected[path] = hashlib.sha256(stream.read()).hexdigest()
        backup = ROOT / "build/ap_bench_config_private_before_station.h"
        if backup.exists():
            raise FileExistsError("Station preparation already has a private backup")
        changed = original.replace('#define WC_STA_SSID ""', '#define WC_STA_SSID ' + json.dumps(ssid))
        changed = changed.replace('#define WC_STA_PASSWORD ""', '#define WC_STA_PASSWORD ' + json.dumps(password))
        patch = "*** Begin Patch\n*** Add File: " + backup.as_posix() + "\n"
        patch += "\n".join("+" + line for line in original.splitlines())
        patch += "\n*** Update File: " + profile.as_posix() + "\n@@\n"
        patch += "\n".join("-" + line for line in original.splitlines()) + "\n"
        patch += "\n".join("+" + line for line in changed.splitlines()) + "\n*** End Patch"
        executable = Path("C:/Users/lenovo/AppData/Local/OpenAI/Codex/bin/f544b3844e0f14e9/codex.exe")
        result = subprocess.run([str(executable), "--codex-run-as-apply-patch", patch],
                                capture_output=True, timeout=20)
        if result.returncode:
            raise RuntimeError("Private apply_patch failed; diagnostic suppressed to protect credentials")
        if profile.read_text(encoding="utf-8").strip() != changed.strip():
            raise ValueError("Private patched profile differs")
        return {"status": "station_profile_prepared_not_flashed", "ssid": ssid,
                "wpa_supplicant_ap_config": configs[0], "passphrase_length": len(password),
                "private_credentials_printed": False, "profile_changed": True,
                "z15_network_changed": False, "motor_gpio_enabled": False,
                "services_before": services, "protected_before": protected,
                "private_ap_config_backup": str(backup),
                "ap_bench_application_rollback": "build/arduino_network_bench/guardianloop_wheelchair.ino.bin"}
    finally:
        if client is not None:
            client.close()
        netsh("JLU.WIFI")
        for _ in range(20):
            state = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], timeout=5).decode(errors="replace")
            if "JLU.WIFI" in state:
                break
            time.sleep(.5)
        print("PC_WIFI_RESTORED " + str("JLU.WIFI" in state), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Use a new report path")
    result = prepare()
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key != "protected_before"}, indent=2))


if __name__ == "__main__":
    main()

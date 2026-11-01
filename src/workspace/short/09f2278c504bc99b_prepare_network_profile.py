"""Generate the ignored Station profile privately; never print credentials."""
import json
from pathlib import Path
import secrets
import subprocess

from audit_z15 import board_connection
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eeg_apps_z15"))
from run_ssvep_backlog_replay import checked

ROOT = Path(__file__).resolve().parent


def main():
    header = ROOT / "firmware/guardianloop_eye_mouse/config_private.h"
    client_config = ROOT / "build/network_private.json"
    if header.exists() or client_config.exists():
        raise FileExistsError("Private profile already exists; do not replace it")
    with board_connection() as client:
        raw = checked(client, "cat /etc/guardianloop/ap.conf", sudo=True)
    values = {}
    for line in raw.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.strip().split("=", 1)
            if name in {"ssid", "psk", "mode", "key_mgmt", "proto"}:
                if name in values:
                    raise ValueError("Ambiguous active AP configuration")
                values[name] = value
    ssid = json.loads(values.get("ssid", '""'))
    password = json.loads(values.get("psk", '""'))
    if (ssid != "GuardianLoop-Z15" or values.get("mode") != "2"
            or values.get("key_mgmt") != "WPA-PSK" or values.get("proto") != "RSN"
            or not 8 <= len(password) <= 63):
        raise ValueError("Unexpected Z15 AP identity/security")
    key = secrets.token_hex(32)
    text = ("#pragma once\n#define PHONE_WIFI_SSID " + json.dumps(ssid)
            + "\n#define PHONE_WIFI_PASSWORD " + json.dumps(password)
            + "\n#define PHONE_AUTH_KEY_HEX " + json.dumps(key) + "\n")
    config = json.dumps({"auth_key": key, "receiver_mac": "28:84:85:60:CD:9C",
                         "receiver_port": 49172}, indent=2) + "\n"
    patch = "*** Begin Patch\n"
    for path, content in ((header, text), (client_config, config)):
        patch += "*** Add File: " + path.as_posix() + "\n"
        patch += "\n".join("+" + line for line in content.splitlines()) + "\n"
    patch += "*** End Patch"
    executable = "C:/Users/lenovo/AppData/Local/OpenAI/Codex/bin/f544b3844e0f14e9/codex.exe"
    result = subprocess.run([executable, "--codex-run-as-apply-patch", patch],
                            capture_output=True, timeout=20)
    if result.returncode or header.read_text(encoding="utf-8").strip() != text.strip():
        raise RuntimeError("Private apply_patch failed; diagnostics suppressed")
    print("Private Wi-Fi Station/HMAC profile prepared; no passwords or key printed; Z15 network unchanged.")


if __name__ == "__main__":
    main()

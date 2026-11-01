#!/usr/bin/env python3
"""Verify the Z15 standalone Wi-Fi dashboard without starting Cyton acquisition."""

import argparse
import json
import time

import paramiko


REMOTE_CHECK = r'''set -u
printf 'kernel='; uname -r
printf 'wifi_module='; lsmod | awk '$1=="8188eu" {print "loaded"; found=1} END {if (!found) print "missing"}'
for service in guardianloop-ap guardianloop-dhcp guardianloop-web guardianloop-cyton; do
    printf '%s.active=' "$service"; systemctl is-active "$service" || true
    printf '%s.enabled=' "$service"; systemctl is-enabled "$service" || true
done
printf 'wlan_type='; iw dev wlan0 info | awk '$1=="type" {print $2}'
printf 'wlan_ssid='; iw dev wlan0 info | awk '$1=="ssid" {$1=""; sub(/^ /,""); print}'
printf 'wlan_ip='; ip -4 -o addr show wlan0 | awk '{split($4,a,"/"); print a[1]}'
printf 'kernel_faults='; if dmesg | grep -Eqi 'Oops|BUG:|kernel panic'; then echo present; else echo none; fi
printf 'api='; curl -fsS http://127.0.0.1:9102/api/status
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.2.99")
    parser.add_argument("--user", default="xilinx")
    parser.add_argument("--password", default="xilinx")
    args = parser.parse_args()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    last_error = None
    for attempt in range(8):
        try:
            client.connect(args.host, username=args.user, password=args.password, timeout=10)
            break
        except (OSError, paramiko.SSHException) as exc:
            last_error = exc
            if attempt == 7:
                raise
            time.sleep(3)
    try:
        _, stdout, stderr = client.exec_command(REMOTE_CHECK, timeout=30)
        output = stdout.read().decode("utf-8", errors="replace")
        errors = stderr.read().decode("utf-8", errors="replace")
        status = stdout.channel.recv_exit_status()
    finally:
        client.close()

    if errors:
        print(errors, end="")
    print(output, end="")
    if status:
        raise SystemExit(status)

    values = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    api = json.loads(values["api"])
    expected = {
        "kernel": "5.4.0-xilinx-v2020.2",
        "wifi_module": "loaded",
        "guardianloop-ap.active": "active",
        "guardianloop-ap.enabled": "enabled",
        "guardianloop-dhcp.active": "active",
        "guardianloop-dhcp.enabled": "enabled",
        "guardianloop-web.active": "active",
        "guardianloop-web.enabled": "enabled",
        "guardianloop-cyton.active": "inactive",
        "guardianloop-cyton.enabled": "disabled",
        "wlan_type": "AP",
        "wlan_ssid": "GuardianLoop-Z15",
        "wlan_ip": "192.168.50.1",
        "kernel_faults": "none",
    }
    failures = [f"{key}: expected {want!r}, got {values.get(key)!r}"
                for key, want in expected.items() if values.get(key) != want]
    system = api.get("system", {})
    if not system.get("ap_active"):
        failures.append("API reports AP inactive")
    if system.get("acquisition_active"):
        failures.append("Cyton acquisition unexpectedly active")
    if failures:
        print("STANDALONE_CHECK_FAILED")
        print("\n".join(failures))
        raise SystemExit(1)
    print("STANDALONE_CHECK_OK")
    print(f"receiver_present={system.get('receiver_present', False)}")
    print(f"brain_data_stale={api.get('stale', True)}")


if __name__ == "__main__":
    main()

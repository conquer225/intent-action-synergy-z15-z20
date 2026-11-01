"""Read the exact spare receiver's Station address and update its ignored config."""
import json
import ipaddress
from pathlib import Path
import subprocess

import serial
from serial_control import check_port, request, NETWORK_PRODUCT

ROOT = Path(__file__).resolve().parent


def main():
    check_port()
    connection = serial.Serial(port=None, baudrate=115200, timeout=.25, write_timeout=2)
    connection.dtr = connection.rts = False
    connection.port = "COM17"
    connection.open()
    try:
        state = request(connection, "STATUS")
        test = request(connection, "SELFTEST")
        if (state.get("product") != NETWORK_PRODUCT or state.get("wifi_connected") is not True
                or state.get("motor_gpio_enabled") is not False or state.get("network_mode") != "off"
                or state.get("busy") or test.get("selftest_passed") is not True
                or state.get("wifi_mac", "").upper() != "28:84:85:60:CD:9C"):
            raise RuntimeError("Spare receiver is not idle on the expected Z15 Station network")
        address = ipaddress.IPv4Address(state["wifi_ip"])
        if address not in ipaddress.IPv4Network("192.168.50.0/24") or address.packed[-1] in (0, 1, 255):
            raise ValueError("Unexpected Station subnet")
    finally:
        connection.close()
    path = ROOT / "build/network_private.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if "receiver_ip" in value:
        raise ValueError("Receiver address already recorded; do not overwrite it")
    # Add only the observed IP; the private key remains outside command output.
    patch = ("*** Begin Patch\n*** Update File: " + path.as_posix()
             + "\n@@\n-  \"receiver_port\": 49172\n+  \"receiver_port\": 49172,\n+  \"receiver_ip\": "
             + json.dumps(str(address)) + "\n*** End Patch")
    executable = "C:/Users/lenovo/AppData/Local/OpenAI/Codex/bin/f544b3844e0f14e9/codex.exe"
    result = subprocess.run([executable, "--codex-run-as-apply-patch", patch], capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError("Private address update failed; diagnostics suppressed")
    with (ROOT / "output/com17_wifi_ble_runtime_20261006.json").open("x", encoding="utf-8") as stream:
        json.dump(dict(state=state, selftest=test), stream, indent=2)
    print(json.dumps(dict(receiver_ip=str(address), mac=state["wifi_mac"], selftest_passed=True,
                          ble_ready=state["ready"], network_mode="off", motor_gpio_enabled=False)))


if __name__ == "__main__":
    main()

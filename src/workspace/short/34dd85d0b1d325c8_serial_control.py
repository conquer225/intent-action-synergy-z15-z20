"""COM17-only diagnostics and explicitly requested manual HID actions."""
import argparse
import json
import sys
from time import monotonic

import serial
from serial.tools import list_ports


PRODUCT = "guardianloop-eye-mouse-0.1.0"
NETWORK_PRODUCT = "guardianloop-eye-mouse-0.2.0"
TARGET_SERIAL = "28848560CD9C"
SAFE_COMMANDS = ("STATUS", "SELFTEST", "STOP")
ACTIONS = ("NEXT", "PREV", "SWIPE_UP", "SWIPE_DOWN",
           "MOVE_LEFT", "MOVE_RIGHT", "MOVE_UP", "MOVE_DOWN")


def check_port():
    ports = [port for port in list_ports.comports() if port.device.upper() == "COM17"]
    if len(ports) != 1:
        raise RuntimeError("COM17 missing or ambiguous; no serial port opened")
    port = ports[0]
    observed = (port.serial_number or "").replace(":", "").upper()
    if port.vid != 0x303A or port.pid != 0x1001 or observed != TARGET_SERIAL:
        raise RuntimeError("COM17 USB identity mismatch; no serial port opened")


def request(connection, command, timeout=5.0):
    connection.write((command + "\n").encode("ascii"))
    connection.flush()
    until = monotonic() + timeout
    while monotonic() < until:
        line = connection.readline()
        try:
            message = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(message, dict):
            continue
        if command == "STATUS" and message.get("product") in (PRODUCT, NETWORK_PRODUCT):
            return message
        if command == "SELFTEST" and "selftest_passed" in message:
            return message
        if command != "STATUS" and ("result" in message or "error" in message):
            return message
    raise TimeoutError(f"No expected response to {command}; no input retried")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", choices=SAFE_COMMANDS + ACTIONS, default="STATUS")
    parser.add_argument("--allow-action", action="store_true",
                        help="Send one manual mouse action, only after the user has the test app open")
    args = parser.parse_args()
    if args.command in ACTIONS and not args.allow_action:
        parser.error("Mouse action requires --allow-action and user confirmation of the foreground app")
    check_port()
    connection = serial.Serial(port=None, baudrate=115200, timeout=0.25, write_timeout=2)
    connection.dtr = False
    connection.rts = False
    connection.port = "COM17"
    connection.open()
    action_attempted = False
    try:
        identity = request(connection, "STATUS")
        expected_wifi = identity.get("product") == NETWORK_PRODUCT
        if (identity.get("motor_gpio_enabled") is not False
                or identity.get("wifi_enabled") is not expected_wifi):
            raise RuntimeError("Unexpected firmware mode; no input action sent")
        if args.command in ACTIONS:
            if identity.get("ready") is not True:
                raise RuntimeError("BLE host not paired/authenticated/subscribed; no mouse action sent")
            if identity.get("busy"):
                raise RuntimeError("An action is already active; no new action sent")
            action_attempted = True
            if request(connection, "ARM").get("result") != "armed":
                raise RuntimeError("Manual ARM rejected; no mouse action sent")
            result = request(connection, args.command)
            print(json.dumps(result))
            if result.get("result") != "action_accepted":
                raise RuntimeError("Manual action rejected; stopping without retry")
            # Drag, release and button-free return take about one second.
            until = monotonic() + 2
            while monotonic() < until:
                state = request(connection, "STATUS")
                if not state.get("busy"):
                    break
        else:
            print(json.dumps(identity if args.command == "STATUS" else request(connection, args.command)))
    finally:
        if action_attempted:
            try:
                print(json.dumps(request(connection, "STOP")))
            except (serial.SerialException, TimeoutError):
                print('{"stop_acknowledged":false,"action_not_retried":true}', file=sys.stderr)
        connection.close()


if __name__ == "__main__":
    main()

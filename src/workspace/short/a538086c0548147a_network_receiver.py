"""Z15-only authenticated one-shot UDP commands; no automatic input retry."""
import hashlib
import hmac
import ipaddress
import json
from pathlib import Path
import re
import secrets
import socket
import time

PRODUCT = "guardianloop-eye-mouse-0.2.0"
OPERATIONS = {"ARM_VIRTUAL", "ARM_HID", "HEARTBEAT", "NEXT", "PREV", "STOP"}


class ReceiverError(Exception):
    pass


def load_config(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(value) != {"auth_key", "receiver_mac", "receiver_port", "receiver_ip"}:
        raise ValueError("Unexpected private receiver configuration")
    address = ipaddress.IPv4Address(value["receiver_ip"])
    if (address not in ipaddress.IPv4Network("192.168.50.0/24")
            or address.packed[-1] in {0, 1, 255} or value["receiver_port"] != 49172
            or value["receiver_mac"].upper() != "28:84:85:60:CD:9C"
            or re.fullmatch(r"[0-9a-f]{64}", value["auth_key"]) is None):
        raise ValueError("Configuration is not the spare COM17 receiver")
    return value


def decode_response(packet, key, nonce):
    if len(packet) > 1024:
        raise ReceiverError("Oversize receiver response")
    body, separator, signature = packet.rpartition(b"|")
    expected = hmac.new(key, body, hashlib.sha256).hexdigest().encode()
    if not separator or not hmac.compare_digest(expected, signature):
        raise ReceiverError("Receiver response authentication failed")
    try:
        value = json.loads(body)
    except (ValueError, UnicodeDecodeError) as error:
        raise ReceiverError("Malformed receiver response") from error
    if (not isinstance(value, dict) or value.get("product") != PRODUCT
            or value.get("nonce") != nonce or value.get("motor_gpio_enabled") is not False
            or re.fullmatch(r"[0-9a-f]{16}", str(value.get("boot_id"))) is None
            or type(value.get("last_sequence")) is not int
            or not 0 <= value["last_sequence"] < 0xffffffff
            or value.get("network_mode") not in {"off", "virtual", "hid"}
            or type(value.get("ble_ready")) is not bool or type(value.get("busy")) is not bool):
        raise ReceiverError("Unexpected receiver identity/state")
    return value


class NetworkReceiver:
    def __init__(self, config):
        self.address = (config["receiver_ip"], config["receiver_port"])
        self.key = bytes.fromhex(config["auth_key"])
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("192.168.50.1", 0))
        self.socket.settimeout(0.12)
        self.boot_id = None

    def close(self):
        self.socket.close()

    def _receive(self, nonce):
        deadline = time.monotonic() + 0.12
        while time.monotonic() < deadline:
            try:
                packet, address = self.socket.recvfrom(1025)
            except socket.timeout as error:
                raise ReceiverError("Receiver timeout; command not retried") from error
            if address != self.address:
                continue
            response = decode_response(packet, self.key, nonce)
            boot = response["boot_id"]
            if self.boot_id is not None and self.boot_id != boot:
                raise ReceiverError("Receiver rebooted; explicit reconnect required")
            self.boot_id = boot
            return response
        raise ReceiverError("Receiver timeout; command not retried")

    def probe(self):
        nonce = secrets.token_hex(8)
        self.socket.sendto(("TICKET|" + nonce).encode(), self.address)
        response = self._receive(nonce)
        if (response.get("result") != "ticket" or response.get("ticket_ms") != 200
                or re.fullmatch(r"[0-9a-f]{16}", str(response.get("ticket"))) is None):
            raise ReceiverError("Receiver did not issue a valid finite ticket")
        return response

    def command(self, operation, source_monotonic=None):
        if operation not in OPERATIONS:
            raise ValueError("Unsupported phone operation")
        response = self.probe()
        if source_monotonic is not None and not 0 <= time.monotonic() - source_monotonic <= 0.25:
            raise ReceiverError("Eye sample became stale before sending; no command sent")
        ticket = response["ticket"]
        sequence = response["last_sequence"] + 1
        text = "G1|{}|{}|{}|{}".format(response["boot_id"], ticket, sequence, operation)
        signature = hmac.new(self.key, text.encode(), hashlib.sha256).hexdigest()
        self.socket.sendto((text + "|" + signature).encode(), self.address)
        result = self._receive(ticket)
        if result["last_sequence"] != sequence:
            raise ReceiverError("Receiver sequence not committed; command not retried")
        expected = {"ARM_VIRTUAL": "armed", "ARM_HID": "armed", "STOP": "stopped",
                    "HEARTBEAT": "heartbeat", "NEXT": "virtual_accepted", "PREV": "virtual_accepted"}
        accepted = {expected[operation]}
        if operation in {"NEXT", "PREV"}:
            accepted.add("hid_accepted")
        if result.get("result") not in accepted:
            raise ReceiverError("Receiver rejected operation: " + str(result.get("result")))
        return result

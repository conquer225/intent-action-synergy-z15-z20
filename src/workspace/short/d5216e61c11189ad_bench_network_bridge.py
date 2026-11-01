"""Explicit bench/remote profiles; manual leases require a fresh phone command."""
import argparse
from http.client import HTTPException
import ipaddress
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from dry_run_bridge import (DirectionPreview, NoRedirect, finite, load_mapping,
                            read_snapshot, reject_constant, validate_source_url)


PRODUCT = "guardianloop-wheelchair-bench-0.1.0"
MOTOR_PRODUCT = "guardianloop-wheelchair-remote-0.1.0"
DIRECTIONS = {"stop", "forward", "backward", "left", "right"}
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


class ReceiverError(Exception):
    """An invalid or unavailable receiver; messages never include the secret key."""


def receiver_url(value):
    parts = urlsplit(value)
    try:
        address = ipaddress.ip_address(parts.hostname)
        port = parts.port or 80
    except (ValueError, TypeError) as error:
        raise ValueError("Receiver needs a literal RFC1918 IPv4 address") from error
    if (parts.scheme != "http" or parts.username is not None or parts.password is not None
            or parts.path not in ("", "/") or parts.query or parts.fragment or port != 80
            or not any(address in network for network in PRIVATE_NETWORKS)):
        raise ValueError("Only a private IPv4 HTTP receiver on port 80 is allowed")
    return "http://" + str(address)


def load_config(path):
    config = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    if not isinstance(config, dict) or set(config) != {"receiver_url", "auth_key"}:
        raise ValueError("Private configuration must contain receiver_url and auth_key only")
    key = config["auth_key"]
    if not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{64}", key) is None:
        raise ValueError("Invalid private authentication key")
    return receiver_url(config["receiver_url"]), key


def require_bench(state, *, motor_test=False):
    product = MOTOR_PRODUCT if motor_test else PRODUCT
    mode = "remote_control" if motor_test else "bench_only"
    if (not isinstance(state, dict) or state.get("firmware") != product
            or state.get("motor_gpio_enabled") is not motor_test
            or state.get("mode") != mode
            or state.get("current_motor_state") != "not_observed"
            or type(state.get("armed")) is not bool
            or type(state.get("software_estop_latched")) is not bool
            or type(state.get("driver_fault")) is not bool
            or state.get("requested_direction") not in DIRECTIONS
            or state.get("lease_ms") != 300 or state.get("max_burst_ms") != 1000):
        raise ReceiverError("Receiver does not match the explicitly selected output profile")
    if motor_test and (state.get('manual_lease_ms') != 500 or type(state.get('manual_active')) is not bool):
        raise ReceiverError('Receiver manual lease profile differs')
    return state


class BenchReceiver:
    def __init__(self, base_url, auth_key, *, motor_test=False):
        if type(motor_test) is not bool:
            raise ValueError("Motor test profile must be explicit")
        self.motor_test = motor_test
        self.base_url = receiver_url(base_url)
        if not isinstance(auth_key, str) or re.fullmatch(r"[0-9a-f]{64}", auth_key) is None:
            raise ValueError("Invalid private authentication key")
        self.auth_key = auth_key
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.verified = False

    def _request(self, path, method="GET", body=None):
        if path not in {"/api/status", "/api/ticket", "/api/command", "/api/stop", "/api/manual-arm"}:
            raise ValueError("Unsupported receiver route")
        headers = {"Cache-Control": "no-store", "Accept": "application/json"}
        if path in {"/api/ticket", "/api/command", "/api/manual-arm"}:
            headers.update({"X-WC-Key": self.auth_key, "Content-Type": "text/plain"})
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=0.25) as response:
                data = response.read(4097)
                if len(data) > 4096:
                    raise ReceiverError("Receiver response exceeds limit")
                if path == "/api/stop":
                    if response.status != 202:
                        raise ReceiverError("Stop request was not acknowledged")
                    return {"stop_request_submitted": True, "physical_stop_observed": False}
                if response.status != 200 or response.headers.get_content_type() != "application/json":
                    raise ReceiverError("Unexpected receiver response")
                return require_bench(json.loads(data, parse_constant=reject_constant), motor_test=self.motor_test)
        except HTTPError as error:
            raise ReceiverError('Receiver '+path+' returned HTTP '+str(error.code)) from None
        except (URLError, OSError, ValueError, HTTPException) as error:
            raise ReceiverError("Receiver request failed: " + type(error).__name__) from None

    def status(self):
        state = self._request("/api/status")
        self.verified = True
        return state

    def stop(self):
        if not self.verified:
            self.status()
        return self._request("/api/stop", "POST", b"")

    def begin_manual(self):
        if not self.motor_test:
            raise ReceiverError('Manual lease requires the remote output profile')
        state = self.status()
        if state['armed'] or state['driver_fault'] or state['software_estop_latched']:
            raise ReceiverError('Receiver is not stopped and available')
        reply = self._request('/api/manual-arm', 'POST', b'')
        if reply.get('ok') is not True or not reply['armed'] or not reply['manual_active']:
            raise ReceiverError('Manual lease was not granted')
        return reply['boot_id']

    def send_direction(self, direction, *, manual_boot=None):
        if direction not in DIRECTIONS or direction == "stop":
            raise ValueError("Use stop() for the STOP intent")
        state = self.status()
        if self.motor_test and (state['manual_active'] != (manual_boot is not None)
                or (manual_boot is not None and state['boot_id'] != manual_boot)):
            self.stop()
            raise ReceiverError('Manual control session ended; select a direction again')
        if not state["armed"] or state["driver_fault"] or state["software_estop_latched"]:
            return {"direction": "stop", "reason": "local_permit_required", "sent": False}
        started = time.monotonic()
        ticket = self._request("/api/ticket", "POST", b"")
        if ticket.get("ok") is not True or ticket["armed"] is not True:
            raise ReceiverError("Ticket was not granted")
        for field in ("boot_id", "sequence"):
            if (not isinstance(ticket.get(field), str)
                    or re.fullmatch(r"[0-9a-f]{16}", ticket[field]) is None
                    or int(ticket[field], 16) == 0):
                raise ReceiverError("Invalid ticket identifier")
        if time.monotonic() - started >= 0.25:
            self.stop()
            return {"direction": "stop", "reason": "ticket_roundtrip_too_slow", "sent": False}
        body = (ticket["boot_id"] + " " + ticket["sequence"] + " " + direction).encode("ascii")
        reply = self._request("/api/command", "POST", body)
        if reply.get("ok") is not True or not reply["armed"] or reply["requested_direction"] != direction:
            raise ReceiverError("Direction was not accepted")
        return {"direction": direction, "reason": "motor_command_accepted" if self.motor_test else "virtual_command_accepted", "sent": True,
                "ticket_and_command_seconds": time.monotonic() - started}


class NetworkBridge:
    def __init__(self, receiver, mapping=None):
        self.receiver = receiver
        self.preview = DirectionPreview(mapping)

    def observe(self, snapshot, now, request_seconds=0, origin="live_readonly_api"):
        if self.receiver.motor_test and origin != "unified_live_hdmi":
            snapshot = None
        preview = self.preview.observe(snapshot, now, request_seconds, origin)
        direction = preview["preview_direction"]
        try:
            if direction == "stop":
                self.receiver.stop()
                result = {"direction": "stop", "reason": preview["reason"], "sent": True}
            else:
                result = self.receiver.send_direction(direction)
        except ReceiverError as error:
            stopped = False
            if self.receiver.verified:
                try:
                    self.receiver.stop()
                    stopped = True
                except ReceiverError:
                    pass
            result = {"direction": "stop", "reason": str(error), "sent": False,
                      "stop_request_submitted": stopped}
        return dict(result, evidence_origin=origin, motor_gpio_enabled=self.receiver.motor_test,
                    physical_motor_output_enabled=self.receiver.motor_test, current_motor_state="not_observed",
                    ssvep_validated_for_driving=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--source-url", type=validate_source_url, required=True)
    parser.add_argument("--mapping", type=Path, default=Path(__file__).with_name("mapping.json"))
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    if not finite(args.seconds) or not 0 < args.seconds <= 60:
        parser.error("seconds must be between 0 and 60")
    base_url, key = load_config(args.config)
    receiver = BenchReceiver(base_url, key)
    receiver.status()
    bridge = NetworkBridge(receiver, load_mapping(args.mapping))
    opener = build_opener(ProxyHandler({}), NoRedirect())
    started = time.monotonic()
    try:
        while time.monotonic() - started < args.seconds:
            sent = time.monotonic()
            try:
                snapshot = read_snapshot(opener, args.source_url)
            except (URLError, OSError, ValueError, HTTPException):
                snapshot = None
            result = bridge.observe(snapshot, time.monotonic(), time.monotonic() - sent)
            print(json.dumps(result, allow_nan=False), flush=True)
            time.sleep(0.1)
    finally:
        if receiver.verified:
            try:
                receiver.stop()
            except ReceiverError:
                print(json.dumps({"stop_request_submitted": False, "physical_stop_observed": False}), flush=True)


if __name__ == "__main__":
    main()

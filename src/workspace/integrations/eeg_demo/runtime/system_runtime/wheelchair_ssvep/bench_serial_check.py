"""Exercise bench-only USB commands; refuses to arm unless motor GPIO is disabled."""
import argparse
import json
from pathlib import Path
import time

import serial


class Bench:
    def __init__(self, port):
        self.serial = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=1)
        self.serial.dtr = False
        self.serial.rts = False
        self.serial.port = port
        self.buffer = bytearray()
        self.verified = False

    def request(self, command):
        self.serial.write(command.encode("ascii") + b"\n")
        finish = time.monotonic() + 3
        while time.monotonic() < finish:
            self.buffer.extend(self.serial.read(min(max(self.serial.in_waiting, 1), 4096)))
            while b"\n" in self.buffer:
                line, _, rest = self.buffer.partition(b"\n")
                self.buffer = bytearray(rest)
                if not line.startswith(b"BENCH {"):
                    continue
                frame = json.loads(line[6:])
                state = frame["state"]
                if (state.get("firmware") != "guardianloop-wheelchair-bench-0.1.0" or
                        state.get("motor_gpio_enabled") is not False or
                        state.get("mode") != "bench_only" or
                        state.get("current_motor_state") != "not_observed"):
                    raise ValueError("Not a motor-disabled bench receiver; no arming allowed")
                self.verified = True
                return frame
            if len(self.buffer) > 8192:
                raise ValueError("Unexpected serial frame length")
        raise TimeoutError("Bench reply not received")

    def stop(self):
        self.serial.write(b"STOP\n")
        time.sleep(0.05)
        return self.request("STATUS")["state"]

    def arm(self):
        state = self.request("ARM")["state"]
        if not state["ok"] or not state["armed"]:
            raise ValueError("Local bench permit denied")

    def ticket(self):
        state = self.request("TICKET")["state"]
        if not state["ok"]:
            raise ValueError("Bench ticket denied")
        return state

    def command(self, ticket, direction):
        return self.request(f"CMD {ticket['boot_id']} {ticket['sequence']} {direction}")["state"]


def run(port, startup_only):
    bench = Bench(port)
    results = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        results.append({"name": name, "passed": True})

    try:
        bench.serial.open()
        time.sleep(0.2)
        initial = bench.request("STATUS")
        check("startup_motor_disabled_stop_disarmed", not initial["state"]["armed"] and
              initial["state"]["requested_direction"] == "stop")
        if startup_only:
            return {"status": "startup_passed", "initial": initial, "checks": results}
        if not initial["link_ready"]:
            return {"status": "waiting_for_phone_ap_connection", "initial": initial, "checks": results}
        check("network_client_present", initial["link_ready"])
        bench.stop()
        check("unarmed_ticket_denied", not bench.request("TICKET")["state"]["ok"])
        for direction in ("forward", "backward", "left", "right"):
            time.sleep(0.75)
            bench.arm()
            ticket = bench.ticket()
            state = bench.command(ticket, direction)
            check(f"virtual_{direction}_accepted", state["ok"] and state["requested_direction"] == direction)
            time.sleep(0.45)
            state = bench.request("STATUS")["state"]
            check(f"{direction}_lease_retracted_without_stop_message", not state["armed"] and
                  state["requested_direction"] == "stop")
        time.sleep(0.4)
        bench.arm()
        ticket = bench.ticket()
        time.sleep(0.35)
        state = bench.command(ticket, "forward")
        check("expired_ticket_rejected", not state["ok"] and not state["armed"])
        bench.arm()
        ticket = bench.ticket()
        check("fresh_ticket_accepted", bench.command(ticket, "forward")["ok"])
        state = bench.command(ticket, "forward")
        check("replayed_ticket_retracts_permit", not state["ok"] and not state["armed"] and
              state["requested_direction"] == "stop")
        time.sleep(0.4)
        bench.arm()
        first = time.monotonic()
        expired = False
        while time.monotonic() - first < 1.4:
            ticket_state = bench.request("TICKET")["state"]
            if not ticket_state["ok"]:
                expired = True
                break
            state = bench.command(ticket_state, "forward")
            if not state["ok"]:
                expired = True
                break
            time.sleep(0.1)
        state = bench.request("STATUS")["state"]
        check("renewals_cannot_extend_one_second_burst", expired and not state["armed"] and
              state["requested_direction"] == "stop")
        time.sleep(0.4)
        bench.arm()
        bench.serial.write(b"ESTOP\n")
        time.sleep(0.05)
        state = bench.request("STATUS")["state"]
        check("software_estop_latches", state["software_estop_latched"] and not state["armed"])
        state = bench.request("ARM")["state"]
        check("arm_cannot_clear_estop", not state["ok"] and not state["armed"])
        state = bench.request("CLEAR")["state"]
        check("local_clear_does_not_arm", not state["software_estop_latched"] and not state["armed"])
        state = bench.stop()
        check("finished_stop_disarmed", not state["armed"] and state["requested_direction"] == "stop")
        return {"status": "passed", "checks": results, "final": state,
                "scope": "USB bench wire and shared owner state machine, not authenticated Wi-Fi direction requests",
                "physical_motor_output_tested": False, "wifi_disconnect_retraction_tested": False}
    finally:
        if bench.serial.is_open:
            if bench.verified:
                bench.serial.write(b"STOP\n")
            bench.serial.close()


def run_disconnect(port, wait_seconds):
    bench = Bench(port)
    try:
        bench.serial.open()
        time.sleep(0.2)
        initial = bench.request("STATUS")
        if not initial["link_ready"]:
            raise ValueError("Connect the phone to the bench AP before the disconnect check")
        bench.stop()
        time.sleep(0.4)
        bench.arm()
        armed = bench.request("STATUS")
        if not armed["state"]["armed"] or armed["state"]["requested_direction"] != "stop":
            raise AssertionError("Disconnect check must start armed but with direction STOP")
        print("READY: motor GPIO disabled, virtual permit armed, direction STOP; disconnect phone Wi-Fi now.", flush=True)
        finish = time.monotonic() + wait_seconds
        while time.monotonic() < finish:
            time.sleep(0.5)
            frame = bench.request("STATUS")
            if not frame["link_ready"]:
                state = frame["state"]
                if state["armed"] or state["requested_direction"] != "stop":
                    raise AssertionError("Network loss did not retract the virtual permit")
                return {"status": "passed", "initial": initial, "before_disconnect": armed,
                        "after_disconnect": frame,
                        "scope": "AP client loss retracts a virtual permit; no direction command or motor output",
                        "wifi_disconnect_permit_retraction_tested": True,
                        "physical_motor_output_tested": False,
                        "physical_stop_latency_measured": False}
        return {"status": "waiting_for_phone_disconnect", "last_observation": frame,
                "wifi_disconnect_permit_retraction_tested": False,
                "physical_motor_output_tested": False}
    finally:
        if bench.serial.is_open:
            if bench.verified:
                bench.serial.write(b"STOP\n")
            bench.serial.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM16")
    parser.add_argument("--startup-only", action="store_true")
    parser.add_argument("--disconnect-check", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=120)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Use a new report path")
    if args.startup_only and args.disconnect_check:
        parser.error("Choose startup-only or disconnect-check")
    if not 1 <= args.wait_seconds <= 180:
        parser.error("wait-seconds must be between 1 and 180")
    result = run_disconnect(args.port, args.wait_seconds) if args.disconnect_check else run(args.port, args.startup_only)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

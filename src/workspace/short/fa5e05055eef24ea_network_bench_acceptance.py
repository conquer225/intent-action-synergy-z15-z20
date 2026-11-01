"""Finite on-Z15 virtual network cases. Local ARM is supplied separately, never over HTTP."""
import argparse
import json
from pathlib import Path
import time

from bench_network_bridge import BenchReceiver, NetworkBridge, load_config
from dry_run_bridge import demo_snapshot


def emit(value):
    print(json.dumps(value, allow_nan=False), flush=True)


def wait_armed(receiver):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if receiver.status()["armed"]:
            return
        time.sleep(.05)
    raise TimeoutError("Local virtual ARM not supplied")


def stopped(receiver):
    state = receiver.status()
    if state["armed"] or state["requested_direction"] != "stop":
        raise AssertionError("Receiver did not retract virtual direction/permit")
    return state


def run(receiver):
    receiver.status()
    receiver.stop()
    checks = []
    try:
        for case in (8, 10, 12, 14, "stop", "no_data", "bad_quality", "stale_input"):
            stopped(receiver)
            emit({"event": "local_arm_required", "case": case, "motor_gpio_enabled": False})
            wait_armed(receiver)
            bridge = NetworkBridge(receiver)
            hz = case if type(case) is int else 8
            result = bridge.observe(demo_snapshot(hz), time.monotonic(), origin="synthetic_network_fixture")
            if not result["sent"] or result["direction"] == "stop":
                raise AssertionError("Virtual direction was not accepted: " + result["reason"])
            if type(case) is int:
                time.sleep(.45)
                final = stopped(receiver)
                check = {"case": case, "passed": True, "direction": result["direction"],
                         "ticket_and_command_seconds": result["ticket_and_command_seconds"],
                         "receiver_lease_retracted_without_sender_stop": True}
            else:
                if case == "stop":
                    receiver.stop()
                else:
                    snapshot = None if case == "no_data" else demo_snapshot()
                    if case == "bad_quality":
                        snapshot["input"]["quality"]["hard_bad"] = True
                    if case == "stale_input":
                        snapshot["input"]["age_seconds"] = 1
                    invalid = bridge.observe(snapshot, time.monotonic(), origin="synthetic_network_fixture")
                    if invalid["direction"] != "stop" or not invalid["sent"]:
                        raise AssertionError("Invalid source did not submit STOP")
                final = stopped(receiver)
                check = {"case": case, "passed": True, "direction": "stop"}
            checks.append(check)
            emit({"event": "case_passed", **check})
            time.sleep(.4)
        return {"status": "passed", "checks": checks, "final_receiver": final,
                "scope": "Z15-to-ESP authenticated HTTP with synthetic SSVEP fixtures; no real EEG identification or GPIO output",
                "real_ssvep_accuracy_tested": False, "physical_motor_output_tested": False}
    finally:
        receiver.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Use a new report path")
    url, key = load_config(args.config)
    result = run(BenchReceiver(url, key))
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    emit(result)


if __name__ == "__main__":
    main()
